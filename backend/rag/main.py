from __future__ import annotations
"""
rag/main.py
Main orchestrator and pipeline execution code for St. Anthony's College EduBot.
Aligned with specification §3 — Pipeline Execution Order (10 stages).
"""

import hashlib
import json
import logging
import random
import re
import time
from typing import Any

# Try relative/absolute imports for llm and db to ensure maximum compatibility
try:
    from llm import generate
except ImportError:
    from ..llm import generate

try:
    from db import collection
except ImportError:
    from ..db import collection

try:
    from reranker import rerank_chunks_with_scores
except ImportError:
    def rerank_chunks_with_scores(query, docs, metas, dists, top_n=10):
        return docs[:top_n], metas[:top_n], dists[:top_n], [0.5] * min(len(docs), top_n)

try:
    from reranker import cross_encoder_available
except ImportError:
    def cross_encoder_available() -> bool:
        # Reranker module missing → scores are uniform fallback; trigger the
        # vector-distance gate rather than trusting the (blind) confidence gate.
        return False

# Local relative imports
from .config import (
    DEBUG_RAG,
    DEFAULT_TOP_K,
    PRINT_FINAL_CONTEXT,
    RAG_MODE,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
    NOT_FOUND_MESSAGE,
    CONFIDENCE_THRESHOLD,
    LLM_PROVIDER,
    KNOWN_DEPARTMENT_NAMES,
    MAX_DISTANCE,
)
from .schemas import make_response
from .text_utils import normalize_query, normalize_text, postprocess_answer
from .prompts import LLM_SYSTEM
from .intent import (
    is_homework_or_assignment,
    is_clearly_out_of_scope,
    is_vague_college_question,
    classify_admission_query,
    detect_query_intents,
    get_primary_intent,
    extract_entities,
    is_eligibility_query,
    extract_personal_eligibility_case,
    extract_role_query,
    extract_staff_department_from_query,
    is_staff_query,
    is_person_lookup_query,
    get_requested_person_title,
    is_course_query,
    is_hostel_query,
    has_personal_situation_context,
    is_procedural_query,
    is_personal_record_query,
    is_list_query,
    detect_programme,
    programme_grounded_in_docs,
    is_programme_specific_query,
    is_programme_availability_query,
    is_bare_umbrella_degree_query,
    query_names_subject,
    UMBRELLA_DEGREES,
)
from .query_expansion import (
    get_casual_response,
    build_smart_query,
    build_smart_retrieval_query,
    build_focused_retrieval_query,
    build_role_retrieval_query,
    expand_query,
    smart_clarification_response,
)
from .filters import build_filter
from .retrieval import (
    retrieve_chunks,
    filter_staff_docs,
    person_lookup_fallback_context,
)
from .responses import (
    homework_refusal_response,
    out_of_scope_response,
    guided_college_response,
    staff_not_found_response,
    not_found_response,
    clarification_response,
    personal_records_refusal_response,
    programme_not_found_response,
)
from .context import build_context
from .table_integrity import degrade_answer_tables
from .response_format import classify_response_format, build_format_instruction
from .scoring import is_context_relevant_for_hostel
from .answer_builders import (
    build_current_principal_answer,
    current_principal_source,
    context_has_likely_person_name_for_title,
    invalid_person_lookup_answer,
    append_supporting_action_details,
)
from .debug import (
    debug_rag,
    debug_person_lookup_blocked,
)
from .cache import get_cached_response, set_cached_response


# §9 Rate limit state — global cooldown
_last_rate_limit_time: float = 0.0
_RATE_LIMIT_COOLDOWN: float = 25.0  # §9: 20-30 seconds randomized jitter


def _log_pipeline(stage: str, message: str, **extra: Any) -> None:
    """Structured pipeline-stage logging (§3)."""
    payload = {"stage": stage, "message": message, **extra}
    logging.info(f"[EduBot Pipeline] {json.dumps(payload, default=str)}")


def verify_faithfulness_logging(answer: str, context: str) -> None:
    """
    Lightweight, non-blocking post-generation check to catch potential hallucinations.
    Logs warning if numbers or code-like tokens in answer are missing from retrieved context.
    """
    import re
    # Regex to find numbers (e.g. 75, 2026, 12) or code-like tokens (e.g. MCA-CC-6000, FYUG)
    tokens = set(re.findall(r'\b(?:[A-Za-z]+-\w+-\w+|\w+-\w+|\d+|[A-Za-z]+\d+\w*)\b', answer))
    
    context_lower = context.lower()
    for token in tokens:
        if token.isalpha() and len(token) < 4:
            continue
        if token.lower() not in context_lower:
            logging.warning(f"[EduBot Faithfulness WARNING] Token '{token}' in LLM answer does not appear in retrieved context (potential hallucination).")


def resolve_answer_citations(answer: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """Remove model citation markup and retain only valid cited source records.

    Invalid citation IDs never erase otherwise valid provenance: if the model
    emits only unknown IDs, the complete retrieved source list is retained.
    Source IDs are not renumbered because they identify the context presented to
    the model.
    """
    text = str(answer or "")
    citation_ids: list[int] = []
    match = re.search(r"Citations:\s*\[([^\]]*)\]", text, re.IGNORECASE)
    if match:
        citation_ids = [int(num) for num in re.findall(r"\d+", match.group(1))]
        text = re.sub(r"\n*Citations:\s*\[[^\]]*\]", "", text, flags=re.IGNORECASE)
    else:
        citation_ids = [
            int(num)
            for num in re.findall(r"\[(?:Source\s+)?(\d+)\]", text, re.IGNORECASE)
        ]

    text = re.sub(r"\[Source\s+\d+\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\(\s*Source\s+\d+\s*\)", "", text, flags=re.IGNORECASE)

    valid_ids = {int(source.get("id")) for source in sources if str(source.get("id", "")).isdigit()}
    requested = set(citation_ids) & valid_ids
    if requested:
        return text, [source for source in sources if source.get("id") in requested]
    return text, sources



def call_llm_with_retry(call_fn: Any, *args: Any,
                        query: str = "", cache_key: str = "",
                        **kwargs: Any) -> str:
    """
    §9 Rate Limit and Error Handling.
    On HTTP 429:
      1. Do NOT retry immediately
      2. Check Layer 1 response cache
      3. If cache hit: return cached response with "(cached response)" note
      4. If cache miss: return busy message
      5. Wait 20-30s randomized jitter before allowing next LLM call
      6. Log rate_limit event
    """
    global _last_rate_limit_time

    # Enforce cooldown from previous rate limit
    elapsed = time.time() - _last_rate_limit_time
    if _last_rate_limit_time > 0 and elapsed < _RATE_LIMIT_COOLDOWN:
        remaining = _RATE_LIMIT_COOLDOWN - elapsed
        _log_pipeline("rate_limit", f"Cooling down, waiting {remaining:.1f}s")
        time.sleep(remaining)

    try:
        return call_fn(*args, **kwargs)
    except Exception as e:
        is_rate_limit = False
        curr_e = e
        while curr_e:
            err_str = str(curr_e).lower()
            if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                is_rate_limit = True
                break
            if hasattr(curr_e, "response") and getattr(curr_e.response, "status_code", None) == 429:
                is_rate_limit = True
                break
            curr_e = getattr(curr_e, "__cause__", None) or getattr(curr_e, "__context__", None)

        if is_rate_limit:
            # §9 Step 6: Log event
            _log_pipeline("rate_limit", "Rate limit hit",
                          query_hash=cache_key,
                          timestamp=time.time(),
                          provider=LLM_PROVIDER)

            # §9 Step 5: Set cooldown (20-30s randomized jitter)
            _last_rate_limit_time = time.time()
            _RATE_LIMIT_COOLDOWN_VAL = random.uniform(20.0, 30.0)

            # §9 Step 2: Check Layer 1 cache
            cached = get_cached_response(query)
            if cached:
                # §9 Step 3: Return cached with note
                answer = cached.get("answer", "")
                _log_pipeline("rate_limit", "Serving cached response")
                return f"{answer}\n\n(cached response)"

            # §9 Step 4: Return busy message
            _log_pipeline("rate_limit", "No cache available, returning busy message")
            return "The assistant is temporarily busy. Please try again in 30 seconds."

        # HTTP 500 / network error → §9
        logging.error(f"[EduBot] LLM call failed: {e}", exc_info=True)
        raise
    return ""


def is_genuinely_ambiguous(query: str) -> bool:
    """Check if query is genuinely ambiguous (does not mention specific courses, abbreviations, or synonyms)."""
    import re
    from .text_utils import ABBREVIATION_MAP
    from .intent import COURSE_ALIASES, PROGRAMME_SYNONYMS, is_vague_college_question
    
    if is_vague_college_question(query):
        return True
        
    q_lower = (query or "").lower()
    words = re.findall(r"\b\w+\b", q_lower)
    
    # Topic-specific keywords that denote a non-ambiguous query
    topic_keywords = {
        "department", "departments", "fee", "fees", "hostel", "hostels",
        "scholarship", "scholarships", "canteen", "placement", "placements",
        "address", "contact", "phone", "email", "faculty", "staff", "teacher",
        "teachers", "principal", "hod", "head", "admission", "admissions",
        "eligibility", "eligible", "syllabus", "syllabi", "exam", "exams",
        "examination", "examinations", "document", "documents", "certificate",
        "certificates", "marksheet", "marksheets", "apply", "registration",
        "activities", "activity", "sports", "clubs", "club", "committee", "committees",
    }
    if any(kw in words for kw in topic_keywords):
        return False
        
    # Check if any abbreviation is explicitly in the query words
    for abbr in ABBREVIATION_MAP:
        if abbr.lower() in words:
            return False
            
    # Check course aliases
    for alias in COURSE_ALIASES:
        if alias.lower() in words:
            return False
            
    # Check programme synonyms
    for prog, syns in PROGRAMME_SYNONYMS.items():
        for syn in syns:
            if syn.lower() in q_lower:
                return False
                
    return True


def ask(
    query: str,
    history: str = "",
    user_id: str | None = None,
    session_id: str | None = None,
    use_personal_docs: bool = False,
    department: str | None = None,
    year: str | None = None,
    document_type: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    try:
        # ── §3 Stage 1: Normalize query ──────────────────────────────────
        filters = {
            "history": history,
            "user_id": user_id,
            "session_id": session_id,
            "use_personal_docs": use_personal_docs,
            "department": department,
            "year": year,
            "document_type": document_type,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "top_k": top_k,
        }

        # ── §3 Stage 2: Generate cache key ───────────────────────────────
        norm_q = normalize_query(query)
        cache_key = hashlib.sha256(norm_q.encode("utf-8")).hexdigest()
        _log_pipeline("cache_key", f"SHA-256: {cache_key[:16]}...", normalized_query=norm_q[:100])

        # ── §3 Stage 3: Cache lookup ─────────────────────────────────────
        cached = get_cached_response(query, filters)
        if cached:
            _log_pipeline("cache", "HIT — returning cached response")
            return cached
        _log_pipeline("cache", "MISS — proceeding with pipeline")

        res = _ask_internal(
            query=query,
            history=history,
            user_id=user_id,
            session_id=session_id,
            use_personal_docs=use_personal_docs,
            department=department,
            year=year,
            document_type=document_type,
            system_prompt=system_prompt,
            temperature=temperature,
            top_k=top_k,
            cache_key=cache_key,
        )

        # §3 Stage 10: store response in cache
        set_cached_response(query, filters, res)
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "answer": f"An internal error occurred: {str(e)}",
            "sources": [],
            "suggestions": [],
            "retrieval_query": query,
            "response_type": "error",
            "error": str(e)
        }


# TODO: split
def _ask_internal(
    query: str,
    history: str = "",
    user_id: str | None = None,
    session_id: str | None = None,
    use_personal_docs: bool = False,
    department: str | None = None,
    year: str | None = None,
    document_type: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    top_k: int | None = None,
    cache_key: str = "",
) -> dict[str, Any]:

    query = (query or "").strip()
    if not query:
        return make_response(
            "Please ask a question about the available college resources.",
            response_type="empty",
        )
    normalized_user_query = normalize_query(query)
    _log_pipeline("normalize", "Query normalized", original=query[:100], normalized=normalized_user_query[:100])

    # ── §3 Stage 4: Vague query gate (rule-based, no model call) ─────────
    if is_personal_record_query(query):
        return personal_records_refusal_response()
        
    if is_homework_or_assignment(query):
        return homework_refusal_response()

    casual = get_casual_response(query)
    if casual:
        _log_pipeline("vague_gate", "Casual/greeting detected — no retrieval")
        return make_response(casual, retrieval_query=query, response_type="casual")

    if is_clearly_out_of_scope(query):
        _log_pipeline("vague_gate", "Out of scope — no retrieval")
        return out_of_scope_response()

    # ── §3 Stage 5: Intent detection (rule-based, no model call) ───────────
    admission_info = classify_admission_query(query)
    personal_case = admission_info.get("category") == "personal_eligibility"
    eligibility_case = extract_personal_eligibility_case(query)
    role_case = extract_role_query(query)
    retrieval_query_raw, latest_user_request, used_history = build_smart_query(
        query=query, history=history,
    )
    # Distill the dense-retrieval query so verbose, conversational phrasing
    # ("Can you give a brief description of …") collapses to its salient phrase,
    # which embeds sharply. Keyword/BM25 retrieval below keeps the expanded query.
    embedding_query_short = build_focused_retrieval_query(retrieval_query_raw)
    retrieval_query = build_smart_retrieval_query(retrieval_query_raw)
    retrieval_query = normalize_query(retrieval_query)

    understanding_query = normalize_query(retrieval_query_raw)
    all_intents = detect_query_intents(understanding_query)
    primary_intent = get_primary_intent(all_intents)
    entities = extract_entities(understanding_query)
    _log_pipeline("intent", f"Detected intents: {all_intents}, primary: {primary_intent}",
                  entities=entities)

    # ── Top-k selection ──────────────────────────────────────────────────────
    is_list = is_list_query(understanding_query)
    from .config import RERANKER_INPUT_K, RERANKER_OUTPUT_K, MIN_RERANKER_SCORE, DEBUG
    try:
        retrieval_count = int(top_k or RERANKER_INPUT_K)
    except Exception:
        retrieval_count = RERANKER_INPUT_K

    retrieval_count = max(3, min(retrieval_count, RERANKER_INPUT_K))
    
    _top_k = 15 if is_list else RERANKER_OUTPUT_K
    _rerank_top_n = 20 if is_list else RERANKER_OUTPUT_K

    # ── Filter build ─────────────────────────────────────────────────────────
    # Namespacing (anti-collision): when the caller did not pin a department but
    # the question clearly targets a KNOWN department, scope retrieval to that
    # department. build_filter uses $in:[dept,"general"], so broadly-tagged
    # ("general") content stays eligible — this never starves recall, it only
    # excludes chunks explicitly tagged to a *different* department, so one
    # department's question cannot pull another department's chunks.
    effective_department = department
    if not effective_department or str(effective_department).lower() == "general":
        detected_dept = entities.get("department")
        if detected_dept and str(detected_dept).lower() in KNOWN_DEPARTMENT_NAMES:
            effective_department = detected_dept
            _log_pipeline("namespace", "Department namespace applied",
                          department=effective_department)

    where_filter = build_filter(
        use_personal_docs=use_personal_docs,
        user_id=user_id,
        department=effective_department,
        year=year,
        document_type=document_type,
    )

    debug_rag("original query", repr(query))
    debug_rag("admission classification", admission_info)
    debug_rag("extracted eligibility case", eligibility_case)
    debug_rag("role_case", role_case)
    debug_rag("smart retrieval query", repr(retrieval_query))
    debug_rag("role retrieval query", repr(build_role_retrieval_query(query)))
    debug_rag("normalized query", repr(normalized_user_query))
    debug_rag("query.expanded", repr(expand_query(retrieval_query)))
    debug_rag("filter", where_filter)
    debug_rag("top_k", _top_k)
    debug_rag("mode", RAG_MODE)
    if DEBUG_RAG:
        try:
            print("RAG COLLECTION COUNT:", collection.count())
            sample = collection.get(limit=5, include=["metadatas"])
            print("RAG SAMPLE METADATA:", sample.get("metadatas", []))
        except Exception as e:
            print("[DEBUG_RAG] collection sample failed:", e)

    # ── §3 Stage 6: Hybrid retrieval ─────────────────────────────────────────
    docs, metas, dists = retrieve_chunks(
        query=retrieval_query,
        top_k=_top_k,
        where_filter=where_filter,
        use_personal_docs=use_personal_docs,
        embedding_query=embedding_query_short,
        original_query=query,
    )
    _log_pipeline("retrieval", f"Retrieved {len(docs)} chunks")
    debug_rag(f"retrieved chunks={len(docs)}")

    # Pre-filtering for staff
    docs, metas, dists = filter_staff_docs(understanding_query, docs, metas, dists)

    # ── §3 Stage 7 + 8: Cross-encoder reranking + Confidence gate ────────
    if docs:
        # Score against the distilled query: conversational filler ("can you give
        # me a brief …") flattens cross-encoder scores to ~0.5 and lets the
        # confidence gate misfire; the salient phrase yields a discriminating
        # spread. Falls back to the full query when distillation found nothing.
        _rerank_q = embedding_query_short or query
        reranked_docs, reranked_metas, reranked_dists, reranker_scores = rerank_chunks_with_scores(
            query=_rerank_q,
            docs=docs,
            metas=metas,
            dists=dists,
            top_n=_rerank_top_n,
        )
        _log_pipeline("rerank", f"Reranked to {len(reranked_docs)} chunks",
                      top_score=reranker_scores[0] if reranker_scores else 0)

        # ── Programme availability verification (anti-hallucination) ─────────
        # If the user names a specific degree programme (e.g. BCA, B.Tech) and that
        # programme does not appear in the retrieved resources, do NOT let the LLM
        # generate admission/eligibility/fee details for it.
        _programme = detect_programme(understanding_query)
        if (
            _programme
            and is_programme_specific_query(understanding_query)
            and not is_bare_umbrella_degree_query(understanding_query)
            and not (_programme in UMBRELLA_DEGREES and query_names_subject(understanding_query))
            and not programme_grounded_in_docs(_programme, reranked_docs)
        ):
            _log_pipeline("programme_gate", "Programme not present in retrieved resources",
                          programme=_programme)
            return programme_not_found_response(
                _programme,
                query=query,
                where_filter=where_filter,
                availability=is_programme_availability_query(query),
                used_history=used_history,
                retrieval_query=retrieval_query,
            )

        # Fix 6: Low confidence hallucination guard (check best reranker score against MIN_RERANKER_SCORE)
        if reranker_scores and reranker_scores[0] < MIN_RERANKER_SCORE:
            _log_pipeline("confidence_gate", f"BLOCKED — top score {reranker_scores[0]} below MIN_RERANKER_SCORE {MIN_RERANKER_SCORE}")
            return make_response(
                "I could not find reliable information about that "
                "in the college documents. Please try rephrasing "
                "your question or contact the college directly.",
                sources=[],
                suggestions=[],
                response_type="not_found",
                retrieval_query=retrieval_query,
                used_history=used_history,
            )

        # §3 Stage 8: Confidence gate (no model call)
        if reranker_scores and reranker_scores[0] < CONFIDENCE_THRESHOLD:
            _log_pipeline("confidence_gate", "BLOCKED — top score below threshold",
                          top_score=reranker_scores[0], threshold=CONFIDENCE_THRESHOLD)
            if is_genuinely_ambiguous(query):
                if is_vague_college_question(query):
                    return guided_college_response(query)
                smart_clarification = smart_clarification_response(query)
                if smart_clarification:
                    return smart_clarification
            return make_response(
                NOT_FOUND_MESSAGE,
                sources=[],
                suggestions=[],
                response_type="not_found",
                retrieval_query=retrieval_query,
                used_history=used_history,
            )
        _log_pipeline("confidence_gate", "PASSED",
                      top_score=reranker_scores[0] if reranker_scores else 0)

        # Robustness gate: when the cross-encoder reranker is unavailable its
        # scores are uniform (~0.5) and the confidence gate above cannot
        # discriminate. In that mode, enforce a hard vector-distance floor so weak
        # matches never reach the LLM — a genuine pre-LLM distance gate (the
        # MAX_DISTANCE check in build_context is only a soft per-chunk drop and is
        # skipped for keyword candidates whose distance is None).
        if not cross_encoder_available():
            usable_dists = [d for d in reranked_dists if d is not None]
            if usable_dists and min(usable_dists) > MAX_DISTANCE:
                _log_pipeline("distance_gate",
                              "BLOCKED — reranker unavailable and best distance beyond MAX_DISTANCE",
                              best_distance=min(usable_dists), max_distance=MAX_DISTANCE)
                return make_response(
                    NOT_FOUND_MESSAGE,
                    sources=[],
                    suggestions=[],
                    response_type="not_found",
                    retrieval_query=retrieval_query,
                    used_history=used_history,
                )

        # Use reranked results going forward
        docs, metas, dists = reranked_docs[:_top_k], reranked_metas[:_top_k], reranked_dists[:_top_k]
        if 'reranker_scores' in locals() and reranker_scores is not None:
            reranker_scores = reranker_scores[:_top_k]

    if not docs:
        # Programme named but nothing retrieved → cannot verify the programme exists.
        _programme = detect_programme(understanding_query)
        if (
            _programme
            and is_programme_specific_query(understanding_query)
            and not is_bare_umbrella_degree_query(understanding_query)
            and not (_programme in UMBRELLA_DEGREES and query_names_subject(understanding_query))
        ):
            return programme_not_found_response(
                _programme,
                query=query,
                where_filter=where_filter,
                availability=is_programme_availability_query(query),
                used_history=used_history,
                retrieval_query=retrieval_query,
            )
        if "staff" in all_intents:
            return staff_not_found_response(entities["department"])
        if personal_case:
            if eligibility_case["is_personal_eligibility"] and entities["course"]:
                return not_found_response(
                    query=retrieval_query,
                    where_filter=where_filter,
                    used_history=used_history,
                    original_query=query,
                )
            if is_genuinely_ambiguous(query):
                smart_clarification = smart_clarification_response(query)
                return smart_clarification or clarification_response()
            return not_found_response(query=retrieval_query, where_filter=where_filter, used_history=used_history, original_query=query)
        if is_genuinely_ambiguous(query):
            if is_vague_college_question(query):
                return guided_college_response(query)
            smart_clarification = smart_clarification_response(query)
            if smart_clarification:
                return smart_clarification
        return not_found_response(query=retrieval_query, where_filter=where_filter, used_history=used_history, original_query=query)

    # ── §3 Stage 9: Context builder ──────────────────────────────────────────
    context, sources = build_context(
        query=retrieval_query,
        docs=docs,
        metas=metas,
        dists=dists,
        # One-line explanation: Pass reranker scores to build_context so they can be stored in the sources.
        reranker_scores=reranker_scores if 'reranker_scores' in locals() else None,
    )
    _log_pipeline("context", f"Built context: {len(context)} chars, {len(sources)} sources")

    if context and not is_person_lookup_query(query) and not is_context_relevant_for_hostel(query, context):
        debug_rag("hostel context rejected as weak or unrelated")
        return make_response(
            NOT_FOUND_MESSAGE,
            sources=[],
            suggestions=[],
            response_type="not_found",
            retrieval_query=retrieval_query,
            used_history=used_history,
        )

    if context and is_person_lookup_query(query):
        valid_sources = [
            source for source in sources
            if context_has_likely_person_name_for_title(query, str(source.get("text") or ""))
        ]
        if not valid_sources or not context_has_likely_person_name_for_title(query, context):
            fallback_context, fallback_sources = person_lookup_fallback_context(
                query=query,
                where_filter=where_filter,
                use_personal_docs=use_personal_docs,
            )
            if fallback_context and fallback_sources:
                context = fallback_context
                sources = fallback_sources
            else:
                debug_person_lookup_blocked(query, context)
                return make_response(
                    NOT_FOUND_MESSAGE,
                    sources=[],
                    suggestions=[],
                    response_type="not_found",
                    retrieval_query=retrieval_query,
                    used_history=used_history,
                )
        else:
            context = "\n\n---\n\n".join(
                (
                    f"[Source {source.get('id')} | File: {source.get('file')} | "
                    f"Page: {source.get('page_label') or source.get('page')} | "
                    f"Section: {source.get('section_title')} | Chunk: {source.get('chunk_index')}]\n"
                    f"{source.get('text') or ''}"
                )
                for source in valid_sources
            )
            sources = valid_sources

    # Confidence Check: If user asked for specific course/eligibility,
    # ensure the context actually mentions it. Bare umbrella-degree queries
    # (e.g. "eligibility for BA") are answerable from the general admission
    # criteria, so they skip this course-name grounding requirement — otherwise a
    # legitimate, answerable question is refused just because the generic degree
    # token isn't repeated verbatim in the eligibility chunks.
    if (
        context
        and ("eligibility" in all_intents or "courses" in all_intents)
        and not is_bare_umbrella_degree_query(query)
    ):
        target_to_check = entities["course"] or entities["department"]
        if target_to_check:
            # Surface forms to look for in a chunk. normalize_query FUSES synonyms
            # into a single multi-word string ("MA" -> "ma master of arts") that
            # never appears verbatim in a document, which made every specific
            # course eligibility query ("MA Education") wrongly fall through to
            # not-found. Match the un-expanded course token AND its
            # subject/department discriminator on whole-word boundaries instead.
            grounding_variants = {
                normalize_text(target_to_check),
                normalize_text(entities.get("course") or ""),
                normalize_text(entities.get("department") or ""),
            }
            grounding_variants = {v for v in grounding_variants if v}
            has_grounding = False
            eligibility_keywords = ["eligibility criteria", "qualifying examination", "subject combination", "required subject", "minimum qualification", "admission criteria"]

            for doc in docs:
                d_l = normalize_text(doc)
                mentions_target = any(
                    re.search(rf"\b{re.escape(v)}\b", d_l) for v in grounding_variants
                )
                if mentions_target:
                    # If they asked for eligibility, we need eligibility keywords.
                    # If they just asked for course info, the course name is enough.
                    if "eligibility" not in all_intents or any(kw in d_l for kw in eligibility_keywords):
                        has_grounding = True
                        break
            
            if not has_grounding and "contact" not in all_intents:
                # If we can't find the specific course/eligibility, don't just show generic stuff.
                return not_found_response(
                    query=retrieval_query,
                    where_filter=where_filter,
                    used_history=used_history,
                    original_query=query,
                )
    if not context:
        if is_person_lookup_query(query):
            fallback_context, fallback_sources = person_lookup_fallback_context(
                query=query,
                where_filter=where_filter,
                use_personal_docs=use_personal_docs,
            )
            if fallback_context and fallback_sources:
                context = fallback_context
                sources = fallback_sources
            else:
                debug_person_lookup_blocked(query, context)
                return make_response(
                    NOT_FOUND_MESSAGE,
                    sources=[],
                    suggestions=[],
                    response_type="not_found",
                    retrieval_query=retrieval_query,
                    used_history=used_history,
                )
        if is_staff_query(query):
            return staff_not_found_response(extract_staff_department_from_query(query))
        if personal_case:
            if eligibility_case["is_personal_eligibility"] and eligibility_case["target_course"]:
                return not_found_response(
                    query=retrieval_query,
                    where_filter=where_filter,
                    used_history=used_history,
                    original_query=query,
                )
            if is_genuinely_ambiguous(query):
                smart_clarification = smart_clarification_response(query)
                return smart_clarification or clarification_response()
            return not_found_response(query=retrieval_query, where_filter=where_filter, used_history=used_history, original_query=query)
        if is_genuinely_ambiguous(query):
            if is_vague_college_question(query):
                return guided_college_response(query)
            smart_clarification = smart_clarification_response(query)
            if smart_clarification:
                return smart_clarification
        return not_found_response(query=retrieval_query, where_filter=where_filter, used_history=used_history, original_query=query)

    if personal_case and not has_personal_situation_context(retrieval_query, context):
        debug_rag("personal exact case not confirmed by context; continuing to safe builders/LLM")

    current_principal_answer = build_current_principal_answer(query, context)
    if current_principal_answer:
        # Cite the tenure evidence that actually proves who is current, not the
        # stale committee tables that dominate retrieval for this query.
        evidence_source = current_principal_source()
        return make_response(
            current_principal_answer,
            sources=[evidence_source] if evidence_source else sources,
            response_type="rag",
            retrieval_query=retrieval_query,
            used_history=used_history,
        )

    # ── LLM generation ───────────────────────────────────────────────────────
    if PRINT_FINAL_CONTEXT:
        print("\n[EduBot] FINAL CONTEXT SENT TO LLM:")
        print(context[:8000])
        print("[EduBot] END CONTEXT\n")

    # Build Intent-Driven LLM Instructions
    intent_rules = []
    if primary_intent == "courses":
        intent_rules.append("- Focus FIRST on listing the available courses or programmes.")
    elif primary_intent == "fees":
        intent_rules.append("- Focus FIRST on the fee structure, amounts, and payment details.")
    elif primary_intent == "eligibility":
        intent_rules.append("- Focus FIRST on specific criteria, marks, and requirements.")
        
    if len(all_intents) > 1:
        other_intents = [i for i in all_intents if i != primary_intent]
        intent_rules.append(f"- Secondary topics to address if found: {', '.join(other_intents)}.")

    target_rule = ""
    if intent_rules:
        target_rule = "Intent priority:\n" + "\n".join(intent_rules) + "\n"

    if personal_case:
        target_val = eligibility_case.get("target_course") or eligibility_case.get("subject")
        if target_val:
            target_rule = f"- IMPORTANT: The user is asking about {target_val}. If the context does NOT contain explicit admission or eligibility criteria specifically for {target_val}, you MUST reply exactly: \"{NOT_FOUND_MESSAGE}\". Do NOT provide generic admission information.\n"
    if is_procedural_query(query):
        target_rule += (
            "- IMPORTANT: This is a procedural question. Answer only with direct steps "
            "or instructions found in the context. Do not include legal, historical, "
            "committee, or background text. If no clear procedure is present, reply exactly: \"I'm sorry, but I don't have that information in the official college resources.\"\n"
        )
    if is_hostel_query(query):
        target_rule += (
            "- IMPORTANT: This is a hostel question. Prefer hostel prospectus, hostel admission, "
            "hostel application form, warden, parent/guardian submission, hostel rules, "
            f"and hostel fee context. If no clear hostel answer is present, reply exactly: \"{NOT_FOUND_MESSAGE}\"\n"
        )
    if is_person_lookup_query(query):
        requested_title = get_requested_person_title(query) or "the requested title"
        target_rule += (
            f"- IMPORTANT: This is a person/title lookup for {requested_title}. Answer only if "
            "the context clearly gives a person name near that title. Do not treat action "
            f"sentences about submitting, paying fees, permission, rules, or forms as names. If no clear name is present, reply exactly: \"{NOT_FOUND_MESSAGE}\"\n"
        )

    system = LLM_SYSTEM
    if target_rule:
        system += f"\n\nAdditional instructions:\n{target_rule}"

    # ── Response-format classification (post-retrieval, pre-generation) ───────
    # Decide the best presentation format from the FINAL reranked context, then
    # steer the generator toward it. Advisory only — the grounding rules above
    # always win, and the instruction itself re-states "never invent rows/cells".
    try:
        _format_decision = classify_response_format(
            query,
            context,
            all_intents=all_intents,
            is_procedural=is_procedural_query(query),
            is_person_lookup=is_person_lookup_query(query),
            is_list=is_list,
        )
        debug_rag(
            "response format",
            f"format={_format_decision.get('format')}",
            f"reason={_format_decision.get('reason')}",
            f"columns={_format_decision.get('columns')}",
        )
        system += "\n\n" + build_format_instruction(_format_decision)
    except Exception as _fmt_err:  # never let formatting break answer generation
        logging.warning(f"[EduBot] response-format classification skipped: {_fmt_err}")
    if system_prompt:
        system += (
            "\n\nAdmin instruction (style/testing only — must not override the document-grounded rules above):\n"
            + system_prompt
        )

    history_block = f"Conversation history:\n{history.strip()}" if history and history.strip() else ""

    prompt = (
        f"Context:\n{context}\n\n"
        + (f"Conversation history:\n{history_block}\n\n" if history_block else "")
        + f"Question:\n{latest_user_request}\n\n"
        "Answer ONLY based on the context above. If you don't know, use the exact fallback phrase.\n"
        "At the very end of your answer, on a new line, write: Citations: [id1, id2, ...] (using the ID from '[Source ID]'). Cite only the sources that directly support your statements."
    )

    final_temperature = 0.0 if temperature is None else temperature

    # DEBUG: prompt size (approx tokens ≈ chars / 4) for the single LLM call.
    debug_rag(
        "prompt sizes",
        f"system_chars={len(system)}",
        f"prompt_chars={len(prompt)}",
        f"approx_tokens={(len(system) + len(prompt)) // 4}",
        f"final_chunks={len(sources)}",
    )
    if DEBUG:
        print(f"[DEBUG] Prompt tokens: {(len(system) + len(prompt)) // 4}")

    # ── §3 Stage 10: Single LLM generation call ─────────────────────────────
    _log_pipeline("llm_call", "Calling LLM", provider=LLM_PROVIDER)

    try:
        answer = call_llm_with_retry(generate, prompt, system_prompt=system, temperature=final_temperature,
                                     query=query, cache_key=cache_key)
    except TypeError:
        try:
            answer = call_llm_with_retry(generate, f"{system}\n\n{prompt}", temperature=final_temperature,
                                         query=query, cache_key=cache_key)
        except Exception as e:
            logging.error(f"[EduBot] LLM generation failed: {e}", exc_info=True)
            return make_response(
                "An error occurred while processing your question. Please try again.",
                sources=[], suggestions=[], response_type="error",
                retrieval_query=retrieval_query, used_history=used_history,
            )
    except Exception as e:
        logging.error(f"[EduBot] LLM generation failed: {e}", exc_info=True)
        return make_response(
            "An error occurred while processing your question. Please try again.",
            sources=[], suggestions=[], response_type="error",
            retrieval_query=retrieval_query, used_history=used_history,
        )

    _log_pipeline("llm_call", "LLM response received", answer_length=len(answer or ""))

    answer, sources = resolve_answer_citations(answer, sources)

    answer = postprocess_answer(answer)
    # The grounding prompt tells the model to reply with NOT_FOUND_MESSAGE *alone*
    # when the context lacks the answer. Models sometimes append that sentinel to a
    # partial attempt instead, producing a self-contradictory reply ("here is some
    # info … I couldn't find this information"). Strip embedded sentinels; if no
    # substantive text remains, restore the bare sentinel so the exact-match
    # not-found routing below still fires.
    _sentinel = NOT_FOUND_MESSAGE.strip()
    if answer and _sentinel in answer and answer.strip() != _sentinel:
        _stripped = answer.replace(_sentinel, "").strip()
        answer = _stripped if len(_stripped) >= 40 else _sentinel
    # Degenerate-output guard: a reply with no real content (e.g. a lone symbol
    # produced by an adversarial or nonsense query) must never be shown as an
    # answer; blank it so the standard no-answer routing below takes over.
    if answer and len(re.sub(r"[^A-Za-z0-9]", "", answer)) < 4:
        _log_pipeline("answer_guard", "BLOCKED — degenerate answer", raw=answer[:40])
        answer = ""
    # Backstop: if the model still rendered a structurally-broken table (placeholder
    # headers, blank cells, collapsed columns) despite the grounding rules, degrade
    # it to the values actually present rather than show a fabricated grid. General;
    # reliable tables are untouched. See rag/table_integrity.py.
    answer = degrade_answer_tables(answer)
    answer = append_supporting_action_details(answer, query, where_filter)
    verify_faithfulness_logging(answer, context)

    if invalid_person_lookup_answer(query, answer):
        return make_response(
            NOT_FOUND_MESSAGE,
            sources=[],
            suggestions=[],
            response_type="not_found",
            retrieval_query=retrieval_query,
            used_history=used_history,
        )

    if not answer:
        if is_genuinely_ambiguous(query):
            smart_clarification = smart_clarification_response(query)
            if smart_clarification:
                return smart_clarification
        return not_found_response(
            query=retrieval_query, where_filter=where_filter,
            used_history=used_history, original_query=query,
        )

    if answer.strip() == NOT_FOUND_MESSAGE.strip():
        if is_genuinely_ambiguous(query):
            smart_clarification = smart_clarification_response(query)
            if smart_clarification:
                return smart_clarification
        return not_found_response(
            query=retrieval_query, where_filter=where_filter,
            used_history=used_history, original_query=query,
        )

    return make_response(
        answer,
        sources=sources,
        suggestions=[],
        retrieval_query=retrieval_query,
        used_history=used_history,
        response_type="rag",
    )
