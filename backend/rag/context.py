"""
rag/context.py
Context builders and sources ranking for St. Anthony's College EduBot.
Imports scoring.py, intent.py, text_utils.py, config.py only at module level.
"""

import logging
import re
from typing import Any

from .config import (
    DEBUG_RAG,
    FEE_TABLE_CONTEXT_CHARS,
    LIST_QUERY_CONTEXT_CHARS,
    MAX_CHARS_PER_CHUNK,
    MAX_CHARS_PER_LIST_CHUNK,
    MAX_CONTEXT_CHARS,
    MAX_DISTANCE,
    MIN_CHUNK_WORDS,
)
from .intent import (
    classify_admission_query,
    extract_hostel_target_from_query,
    extract_role_query,
    extract_exact_topic,
    is_activity_query,
    is_application_fee_query,
    is_attendance_query,
    is_certificate_course_query,
    is_cell_or_committee_query,
    is_club_query,
    is_criteria_query,
    is_document_overview_query,
    is_fee_table_query,
    is_head_query,
    is_list_query,
    is_staff_query,
    is_warden_query,
    is_website_links_query,
)
from .scoring import (
    _criteria_heading_for_query,
    admission_evidence_score,
    attendance_relevance_score,
    chunk_has_staff_evidence,
    club_relevance_score,
    activity_relevance_score,
    course_relevance_score,
    criteria_relevance_score,
    department_relevance_score,
    document_evidence_score,
    fee_evidence_score,
    hostel_evidence_score,
    hostel_relevance_score,
    is_table_of_contents_chunk,
    keyword_score,
    metadata_boost_score,
    person_lookup_relevance_score,
    procedural_relevance_score,
    role_evidence_score,
    staff_relevance_score,
)
from .text_utils import (
    clean_text,
    important_words,
    normalize_text,
)


def debug_rag(message: str, *values: Any) -> None:
    """Redirect debug statements to the logging module when DEBUG_RAG is active."""
    if DEBUG_RAG:
        logging.info(f"[DEBUG_RAG] {message} " + " ".join(map(str, values)))


# TODO: split
def focus_text_for_query(query: str, document: str, max_chars: int) -> str:
    """Return up to max_chars of the document anchored near the most relevant passage."""
    cleaned = clean_text(document)
    if len(cleaned) <= max_chars:
        return cleaned

    d_norm = normalize_text(cleaned)
    anchors: list[str] = []

    topic = extract_role_query(query).get("target") or extract_exact_topic(query)
    if topic:
        anchors.append(topic)
    if is_attendance_query(query):
        anchors.extend(["attendance", "75%", "75 percent", "leave requirements"])
    if is_application_fee_query(query):
        anchors.extend(["application fee", "application fees", "non-refundable application fee"])
    admission_info = classify_admission_query(query)
    admission_category = str(admission_info.get("category") or "")
    if admission_category.startswith("admission") or admission_category in {"eligibility", "personal_eligibility", "merit_selection", "reservation"}:
        anchors.extend([
            "admission", "application", "eligibility", "qualifying examination",
            "minimum marks", "merit list", "selection", "entrance test", "last date",
            "notice", "notification", "counselling",
        ])
    if admission_category == "documents":
        anchors.extend([
            "documents required", "certificates", "marksheet", "transfer certificate",
            "migration certificate", "character certificate", "original documents",
        ])
    if is_warden_query(query):
        target = extract_hostel_target_from_query(query)
        if target:
            anchors.append(target)
        anchors.extend(["warden", "hostel warden", "hall warden", "superintendent", "hostel", "hall"])
    if is_certificate_course_query(query):
        anchors.extend(["certificate courses", "certificate", "career oriented", "add-on courses", "skill courses"])
    if any(term in normalize_text(query) for term in ["placement", "career guidance", "sds"]):
        anchors.extend(["placement", "placements", "career guidance", "career counselling", "student development services", "sds", "workshops", "coaching"])
    if "facilities" in normalize_text(query):
        anchors.extend(["facilities", "campus facilities", "library", "laboratories", "hostel", "medical aid", "ambulance", "gymnasium", "sports", "counselling", "wifi"])
    if is_club_query(query):
        anchors.extend(["club", "clubs", "association", "society"])
    if is_activity_query(query):
        anchors.extend(["co-curricular", "extension activities", "clubs", "ncc", "nss", "rovers", "rangers", "sac-seva", "social outreach", "seminars", "workshops", "guest lectures", "sports", "cultural"])
    if is_website_links_query(query):
        anchors.extend(["quick links", "useful links", "important links", "downloads", "website links", "notices"])

    for word in important_words(query):
        if word not in anchors:
            anchors.append(word)

    best_position = -1
    for anchor in anchors:
        if not anchor:
            continue
        pos = d_norm.find(normalize_text(anchor))
        if pos != -1:
            best_position = pos
            break

    if best_position == -1:
        return cleaned[:max_chars]

    start = max(0, best_position - 220)
    end   = min(len(cleaned), start + max_chars)
    return cleaned[start:end].strip()


# TODO: split
def build_context(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    # One-line explanation: Accept optional list of reranker scores to include in final sources.
    reranker_scores: list[float] | None = None,
) -> tuple[str, list[dict]]:
    """Assemble final context string prepending metadata and format sources."""
    context_parts: list[str] = []
    sources: list[dict]      = []
    total_chars = 0

    fee_table_query = is_fee_table_query(query)
    if fee_table_query:
        # Full fee structure spans several consecutive prospectus pages; widen the
        # budget so Laboratory/Refundable/One-Time sections are not truncated away.
        context_limit = FEE_TABLE_CONTEXT_CHARS
    elif is_list_query(query) or is_document_overview_query(query):
        context_limit = LIST_QUERY_CONTEXT_CHARS
    else:
        context_limit = MAX_CONTEXT_CHARS

    if fee_table_query:
        # Fee pages carry long itemised tables; keep each chunk intact so no line
        # items are trimmed mid-table.
        chunk_char_limit = 2600
    elif is_warden_query(query) or is_certificate_course_query(query):
        chunk_char_limit = 2600
    elif is_staff_query(query) or is_cell_or_committee_query(query) or is_head_query(query):
        chunk_char_limit = 2200
    elif is_list_query(query) or is_document_overview_query(query) or is_activity_query(query):
        chunk_char_limit = 1800
    else:
        chunk_char_limit = MAX_CHARS_PER_LIST_CHUNK if is_list_query(query) else MAX_CHARS_PER_CHUNK

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        meta = meta or {}
        try:
            # One-line explanation: Convert distance to float if it is not None.
            distance = float(dist) if dist is not None else None
        except Exception:
            distance = 999.0

        # One-line explanation: Extract the rerank score corresponding to the current chunk index if available.
        rerank_score = None
        if reranker_scores is not None and (i - 1) < len(reranker_scores):
            rerank_score = float(reranker_scores[i - 1])

        lexical_score = keyword_score(query, doc)
        evidence_score = (
            admission_evidence_score(query, doc)
            + document_evidence_score(query, doc)
            + role_evidence_score(query, doc)
            + fee_evidence_score(query, doc)
            + hostel_evidence_score(query, doc)
            + metadata_boost_score(query, doc, meta)
            + hostel_relevance_score(query, doc, meta) * 120.0
            + procedural_relevance_score(query, doc, meta) * 90.0
            + person_lookup_relevance_score(query, doc, meta) * 140.0
        )
        if is_table_of_contents_chunk(doc) and "contents" not in normalize_text(query):
            continue
        # One-line explanation: Check that distance is not None before comparing to MAX_DISTANCE.
        if distance is not None and distance > MAX_DISTANCE and (lexical_score + evidence_score) < 80.0:
            debug_rag(
                "context drop",
                f"reason=distance distance={distance:.4f}",
                f"evidence={lexical_score + evidence_score:.2f}",
                f"file={meta.get('filename')}",
                f"page={meta.get('page')}",
            )
            continue

        cleaned = focus_text_for_query(query, doc, chunk_char_limit)
        if len(cleaned.split()) < MIN_CHUNK_WORDS:
            continue

        filename      = meta.get("filename", "Unknown document")
        page          = meta.get("page", "?")
        page_label    = meta.get("page_label") or page
        chunk_index   = meta.get("chunk_index", "?")
        section_title = meta.get("section_title", "general")
        source_url    = str(meta.get("source_url", "") or "")
        source_url_line = f" | URL: {source_url}" if source_url else ""

        # Surface provenance/recency so the LLM can DATE each source and resolve
        # conflicts per the system prompt's freshness rule (it references
        # document_year/document_date/source_type, which were previously never
        # shown in the context). When two sources disagree, the model can now name
        # both and say which is more recent.
        doc_year = str(meta.get("document_year", "") or "").strip()
        doc_date = str(meta.get("document_date", "") or "").strip()
        src_type = str(meta.get("source_type", "") or "").strip()
        provenance_bits = []
        if src_type and src_type.lower() not in ("", "unknown"):
            provenance_bits.append(f"Type: {src_type}")
        if doc_year and doc_year.lower() not in ("", "general", "0"):
            provenance_bits.append(f"Year: {doc_year}")
        if doc_date and doc_date.lower() not in ("", "general"):
            provenance_bits.append(f"Date: {doc_date}")
        provenance_line = (" | " + " | ".join(provenance_bits)) if provenance_bits else ""

        # Human-friendly document name for citations (e.g. "Prospectus 2026")
        # so the LLM can cite without exposing the raw filename. Tier 1 canonical
        # sources resolve to their display name; others fall back to a tidied
        # filename via rag/authority.py.
        try:
            from .authority import display_name_for
            display_name = display_name_for(meta)
        except Exception:
            display_name = filename
        header = (
            f"[Source {i} | Document: {display_name} | File: {filename} | "
            f"Page: {page_label} | Section: {section_title} | "
            f"Chunk: {chunk_index}{source_url_line}{provenance_line}]\n"
        )
        part = header + cleaned
        if total_chars + len(part) > context_limit:
            print(f"[RAG] Limit reached: Context builder reached limit ({context_limit} chars). Dropping remaining chunk {i} to avoid mid-sentence truncation.")
            break

        context_parts.append(part)
        total_chars += len(part)
        sources.append({
            "id":            i,
            "file":          filename,
            "page":          page,
            "page_label":    page_label,
            "chunk_index":   chunk_index,
            "text":          cleaned,
            "distance":      distance,
            # One-line explanation: Store the actual vector distance (or None if fallback 999.0 or missing) in a separate field.
            "vector_distance": distance if distance != 999.0 else None,
            "rerank_score":  rerank_score,
            "keyword_score": lexical_score + evidence_score,
            "scope":         meta.get("scope", "unknown"),
            "department":    meta.get("department", "general"),
            "year":          meta.get("year", "general"),
            "document_type": meta.get("document_type", "general"),
            "section_title": section_title,
            "source_url":    source_url,
            "found_on_url":  str(meta.get("found_on_url", "") or ""),
            "source_pdf_filename": str(meta.get("source_pdf_filename", "") or ""),
            "file_type":     str(meta.get("file_type", "") or ""),
            "source_type":   str(meta.get("source_type", "") or ""),
            "crawl_base_url": str(meta.get("crawl_base_url", "") or ""),
        })

    debug_rag(f"context chars={total_chars}")
    debug_rag(f"sources sent to llm={len(sources)}")
    return "\n\n---\n\n".join(context_parts), rank_sources_for_query(query, sources)


def rank_sources_for_query(query: str, sources: list[dict]) -> list[dict]:
    """Rank the sources for the query based on relevant details and boosts."""
    ranked: list[tuple[float, float, int, dict]] = []
    heading     = _criteria_heading_for_query(query) if is_criteria_query(query) else None
    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)

    # The displayed reference list must point at the document the answer actually
    # came from. The cross-encoder rerank_score is the best available relevance
    # signal for that, but it goes near-flat (~0.50) on verbose conversational
    # queries (see retrieval-architecture notes), where its tiny spread is noise.
    # So we only let rerank_score lead the ordering when it is meaningfully
    # discriminating; otherwise we keep the existing keyword/relevance ordering
    # untouched. This changes display order only — never retrieval or the answer.
    rerank_values = [
        float(s.get("rerank_score"))
        for s in sources
        if s.get("rerank_score") is not None
    ]
    use_rerank = (
        len(rerank_values) >= 2
        and (max(rerank_values) - min(rerank_values)) >= 0.08
    )

    for idx, source in enumerate(sources):
        text  = source.get("text", "")
        score = float(source.get("keyword_score") or 0.0)
        source_meta = {
            "filename": source.get("file"),
            "section_title": source.get("section_title"),
            "source_pdf_filename": source.get("source_pdf_filename"),
        }
        score += hostel_relevance_score(query, text, source_meta) * 120.0
        score += procedural_relevance_score(query, text, source_meta) * 90.0
        score += person_lookup_relevance_score(query, text, source_meta) * 140.0
        if is_criteria_query(query):
            score += criteria_relevance_score(query, text)
            if heading and heading in normalize_text(text):
                score += 5000.0
        if exact_topic and exact_topic in normalize_text(text):
            score += 1200.0
        rerank_primary = (
            float(source.get("rerank_score") or 0.0) if use_rerank else 0.0
        )
        ranked.append((rerank_primary, score, idx, source))

    # Primary key: rerank relevance (only when discriminating). Secondary key:
    # the existing keyword/relevance score — which is also the sole key whenever
    # rerank is flat or unavailable, preserving prior behavior exactly.
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for _rerank, _score, _idx, source in ranked:
        source_url = str(source.get("source_url") or "").strip()
        if source_url:
            key = (
                source_url,
                str(source.get("page_label") or source.get("page") or "?"),
                str(source.get("chunk_index", "?")),
            )
        else:
            key = (
                str(source.get("file") or "unknown"),
                str(source.get("page_label") or source.get("page") or "unknown"),
            )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped
