from __future__ import annotations

"""
rag/retrieval.py
Lexical and vector search retrieval orchestration for St. Anthony's College EduBot.
Imports config.py, intent.py, text_utils.py, filters.py, scoring.py, query_expansion.py, answer_builders.py,
and external db.py, embeddings.py, and reranker.py.
"""

import hashlib
import logging
import re
from typing import Any

from db import collection
from embeddings import encode_query

try:
    from reranker import rerank_chunks
except ImportError:
    def rerank_chunks(
        query: str,
        docs: list[str],
        metas: list[dict],
        dists: list[float],
        top_n: int = 5,
    ) -> tuple[list[str], list[dict], list[float]]:
        return docs[:top_n], metas[:top_n], dists[:top_n]

from .config import (
    DEBUG_RAG,
    KEYWORD_CANDIDATES,
    RETRIEVAL_CANDIDATES,
    RERANK_TOP_N,
    MAX_RELATED_CHUNKS,
)
from .intent import (
    extract_role_query,
    extract_exact_topic,
    is_contact_query,
    is_attendance_query,
    is_club_query,
    is_head_query,
    is_fee_query,
    is_application_fee_query,
    is_list_query,
    is_department_query,
    is_document_overview_query,
    is_course_query,
    is_criteria_query,
    is_specific_query,
    is_cell_or_committee_query,
    is_activity_query,
    is_hostel_query,
    is_procedural_query,
    is_person_lookup_query,
    is_staff_query,
    get_requested_person_title,
    extract_staff_department_from_query,
    extract_department_from_query,
    classify_admission_query,
    _dept_aliases,
    expand_person_lookup_query,
    chunk_looks_like_course_only,
    chunk_has_staff_evidence,
    is_postgraduate_course_query,
    is_certificate_course_query,
)
from .text_utils import (
    important_words,
    normalize_text,
    normalize_query,
    clean_text,
    content_without_context_header,
    rerank_text,
)
from .filters import metadata_allows_query, candidate_dedupe_key
from .scoring import (
    keyword_score,
    metadata_boost_score,
    staff_relevance_score,
    role_evidence_score,
    current_role_evidence_score,
    has_head_marker_near_topic,
    attendance_relevance_score,
    fee_evidence_score,
    department_relevance_score,
    course_relevance_score,
    criteria_relevance_score,
    club_relevance_score,
    activity_relevance_score,
    admission_evidence_score,
    document_evidence_score,
    hostel_evidence_score,
    contact_marker_score,
    hostel_relevance_score,
    procedural_relevance_score, # This line is already present in the original file.
    person_lookup_relevance_score,
    score_chunk_by_intent,
    _criteria_heading_for_query,
    is_website_links_query,
    is_toc_candidate,
)
from .query_expansion import expand_query, extract_query_constraints


def _is_curriculum_request(query: str) -> bool:
    q = normalize_query(query)
    return bool(re.search(
        r"\b(syllabus|syllabi|curriculum|curricula|papers?|modules?)\b",
        q,
    )) or ("semester" in q and bool(re.search(r"\bsubjects?\b", q)))


def _curriculum_evidence_matches(query: str, doc: str, meta: dict | None) -> bool:
    """Require actual curriculum structure plus the user's hard constraints."""
    if not _is_curriculum_request(query):
        return True

    constraints = extract_query_constraints(query)
    meta = meta or {}
    hay = normalize_text(rerank_text(doc, meta))
    if not any(marker in hay for marker in (
        "syllabus", "curriculum", "course code", "course structure",
        "structure of the syllabus", "name of course", "title of the course",
    )):
        return False

    programme = constraints.get("programme")
    if programme:
        from .intent import PROGRAMME_SYNONYMS

        filename_scope = normalize_text(
            f"{meta.get('filename', '')} {meta.get('section_title', '')} "
            f"{meta.get('programme', '')}"
        )
        synonyms = PROGRAMME_SYNONYMS.get(str(programme), [str(programme).lower()])
        full_forms = [normalize_text(s) for s in synonyms if len(s.split()) > 1]
        code = normalize_text(str(programme))
        programme_match = (
            any(form in hay for form in full_forms)
            or bool(re.search(rf"\b{re.escape(code)}\b", filename_scope))
            or bool(re.search(rf"\b{re.escape(code)}\b", hay[:1200]))
        )
        if not programme_match:
            return False

    department = normalize_text(str(constraints.get("department") or ""))
    if department:
        department_scope = normalize_text(
            f"{meta.get('department', '')} {meta.get('filename', '')} "
            f"{meta.get('section_title', '')} {hay[:1200]}"
        )
        if not re.search(rf"\b{re.escape(department)}\b", department_scope):
            return False

    semester = constraints.get("semester")
    if semester:
        number_roman = {
            "first": ("1", "i"), "second": ("2", "ii"),
            "third": ("3", "iii"), "fourth": ("4", "iv"),
            "fifth": ("5", "v"), "sixth": ("6", "vi"),
            "seventh": ("7", "vii"), "eighth": ("8", "viii"),
        }
        number, roman = number_roman[str(semester)]
        suffix = {"1": "st", "2": "nd", "3": "rd"}.get(number, "th")
        semester_match = re.search(
            rf"\b(?:{semester}\s+semester|semester\s+{number}|{number}{suffix}\s+semester|"
            rf"semester\s+{roman}|{number}{suffix}\s+sem)\b",
            hay,
        )
        if not semester_match:
            return False

    return True
from .answer_builders import context_has_likely_person_name_for_title
from .context import build_context
from .freshness import freshness_rank_items, drop_superseded_duplicates


def debug_rag(message: str, *values: Any) -> None:
    """Redirect debug statements to the logging module when DEBUG_RAG is active."""
    if DEBUG_RAG:
        logging.info(f"[DEBUG_RAG] {message} " + " ".join(map(str, values)))


# TODO: split
def metadata_matches_where_filter(meta: dict | None, where_filter: dict | None) -> bool:
    if not where_filter:
        return True
    meta = meta or {}
    
    # Check for $and condition
    if "$and" in where_filter:
        for sub_filter in where_filter["$and"]:
            if not metadata_matches_where_filter(meta, sub_filter):
                return False
        return True
        
    # Standard single key filter (e.g. {"deleted": {"$eq": False}})
    for key, condition in where_filter.items():
        val = meta.get(key)
        if isinstance(condition, dict):
            for op, target_val in condition.items():
                if op == "$eq":
                    if val != target_val:
                        return False
                elif op == "$ne":
                    if val == target_val:
                        return False
                elif op == "$in":
                    val_str = str(val).lower() if val is not None else ""
                    target_list_str = [str(x).lower() for x in target_val]
                    if val_str not in target_list_str:
                        return False
                elif op == "$nin":
                    val_str = str(val).lower() if val is not None else ""
                    target_list_str = [str(x).lower() for x in target_val]
                    if val_str in target_list_str:
                        return False
        else:
            if val != condition:
                return False
                
    return True


# TODO: split
def keyword_retrieve_chunks(
    query: str,
    where_filter: dict | None,
    limit: int = KEYWORD_CANDIDATES,
    use_personal_docs: bool = False,
) -> tuple[list[str], list[dict], list[float]]:
    try:
        from .bm25_index import get_all_documents_and_metas, bm25_retrieve, load_bm25_index
        from .bm25_index import _bm25_model

        if _bm25_model is None:
            load_bm25_index()

        all_docs, all_metas = get_all_documents_and_metas()
        
        if all_docs:
            from .intent import is_list_query
            if not is_list_query(query):
                cand_docs, cand_metas, _ = bm25_retrieve(query, top_k=300)
            else:
                cand_docs, cand_metas, _ = bm25_retrieve(query, top_k=500)
            if not cand_docs:
                return [], [], []
        else:
            cand_docs, cand_metas = None, None

        scored: list[tuple[float, str, dict]] = []
        exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)
        strict_exact_topic = (
            exact_topic
            if exact_topic and not (is_contact_query(query) or is_attendance_query(query) or is_club_query(query))
            else None
        )
        q_words = important_words(exact_topic or query)
        role_case = extract_role_query(query)
        role = role_case.get("role")
        role_terms: list[str] = []
        if role:
            role_terms.append(role)
            if role == "hod":
                role_terms.extend(["hod", "head", "head of department"])
            elif role == "warden":
                role_terms.extend(["hostel warden", "hall warden", "superintendent"])

        if cand_docs is not None:
            for doc, meta in zip(cand_docs, cand_metas):
                meta = meta or {}
                if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                    continue
                if not metadata_matches_where_filter(meta, where_filter):
                    continue

                score  = keyword_score(query, doc) + metadata_boost_score(query, doc, meta)
                score += staff_relevance_score(query, doc, meta)
                d_norm = normalize_text(doc)
                body_norm = normalize_text(content_without_context_header(doc))

                if strict_exact_topic:
                    if strict_exact_topic in body_norm:
                        score += 300.0
                    elif is_specific_query(query):
                        score -= 120.0

                if is_website_links_query(query) and meta.get("source_type") == "website_links":
                    score += 1500.0

                if role_terms:
                    if any(term and term in d_norm for term in role_terms):
                        score += 180.0
                    elif role_evidence_score(query, doc) < 450.0:
                        score -= 60.0
                elif is_head_query(query) and not has_head_marker_near_topic(doc, exact_topic):
                    score += role_evidence_score(query, doc) - 40.0
                if is_attendance_query(query) and attendance_relevance_score(doc) < 300.0:
                    score -= 80.0
                if is_fee_query(query) and fee_evidence_score(query, doc) < 250.0:
                    score -= 80.0

                from .intent import is_list_query
                if not is_list_query(query):
                    if not exact_topic and q_words and not any(w in d_norm for w in q_words):
                        score -= 60.0

                if score > 0:
                    scored.append((score, doc, meta))
        else:
            batch_size = 500
            offset = 0
            while True:
                kwargs: dict[str, Any] = {
                    "include": ["documents", "metadatas"],
                    "limit": batch_size,
                    "offset": offset,
                }
                if where_filter:
                    kwargs["where"] = where_filter

                result = collection.get(**kwargs)
                all_docs  = result.get("documents", [])
                all_metas = result.get("metadatas", [])
                if not all_docs:
                    break

                for doc, meta in zip(all_docs, all_metas):
                    meta = meta or {}
                    if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                        continue

                    score  = keyword_score(query, doc) + metadata_boost_score(query, doc, meta)
                    score += staff_relevance_score(query, doc, meta)
                    d_norm = normalize_text(doc)
                    body_norm = normalize_text(content_without_context_header(doc))

                    if strict_exact_topic:
                        if strict_exact_topic in body_norm:
                            score += 300.0
                        elif is_specific_query(query):
                            score -= 120.0

                    if is_website_links_query(query) and meta.get("source_type") == "website_links":
                        score += 1500.0

                    if role_terms:
                        if any(term and term in d_norm for term in role_terms):
                            score += 180.0
                        elif role_evidence_score(query, doc) < 450.0:
                            score -= 60.0
                    elif is_head_query(query) and not has_head_marker_near_topic(doc, exact_topic):
                        score += role_evidence_score(query, doc) - 40.0
                    if is_attendance_query(query) and attendance_relevance_score(doc) < 300.0:
                        score -= 80.0
                    if is_fee_query(query) and fee_evidence_score(query, doc) < 250.0:
                        score -= 80.0

                    from .intent import is_list_query
                    if not is_list_query(query):
                        if not exact_topic and q_words and not any(w in d_norm for w in q_words):
                            score -= 60.0

                    if score > 0:
                        scored.append((score, doc, meta))

                if len(all_docs) < batch_size:
                    break
                offset += batch_size

        scored.sort(key=lambda item: item[0], reverse=True)
        docs  = [item[1] for item in scored[:limit]]
        metas = [item[2] for item in scored[:limit]]
        # One-line explanation: Set default distance to None for keyword search to indicate lack of vector distance score.
        dists = [None] * len(docs)
        debug_rag(f"keyword candidates={len(docs)} limit={limit}")
        if DEBUG_RAG:
            from .debug import debug_print_chunks
            debug_print_chunks(query, docs, metas, [item[0] for item in scored[:limit]], title="KEYWORD RESULTS")
        return docs, metas, dists
    except Exception as e:
        print(f"[EduBot] Keyword retrieval failed: {e}")
        return [], [], []


# TODO: split
def special_list_keyword_retrieve(
    query: str,
    where_filter: dict | None,
    use_personal_docs: bool = False,
    limit: int = 60,
) -> tuple[list[str], list[dict], list[float]]:
    if not (
        is_department_query(query)
        or is_course_query(query)
        or is_club_query(query)
        or is_cell_or_committee_query(query)
        or is_website_links_query(query)
        or is_activity_query(query)
        or is_hostel_query(query)
        or is_procedural_query(query)
        or is_person_lookup_query(query)
        or is_staff_query(query)
    ):
        return [], [], []

    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        from .bm25_index import _bm25_model

        if _bm25_model is None:
            load_bm25_index()

        all_docs, all_metas = get_all_documents_and_metas()

        matched: list[tuple[float, str, dict]] = []
        markers: list[str] = []
        if is_department_query(query) and not is_course_query(query):
            markers.extend(["department of", "departments", "academic departments"])
        if is_course_query(query):
            markers.extend([
                "course", "courses", "programme", "programmes",
                "undergraduate", "postgraduate", "degree",
                "b.a", "b.sc", "b.com", "bba", "bca", "m.a", "m.sc", "m.com",
                "diploma", "certificate", "pg", "ug", "master", "bachelor", "msw", "mca",
            ])
        if is_club_query(query) or is_cell_or_committee_query(query):
            markers.extend([
                "club", "clubs", "cell", "cells", "committee", "committees",
                "association", "associations", "society", "societies",
            ])
        if is_activity_query(query):
            markers.extend([
                "student activities", "activity", "activities",
                "co-curricular", "co curricular", "extracurricular", "extra curricular",
                "event", "events", "seminar", "seminars", "workshop", "workshops",
                "guest lecture", "guest lectures", "social outreach", "sac seva", "sac-seva",
                "sports", "cultural", "ncc", "nss", "rovers", "rangers",
            ])
        if is_hostel_query(query):
            markers.extend([
                "hostel", "hostel admission", "hostel application", "application form",
                "warden", "parent", "guardian", "boys hostel", "girls hostel",
                "hostel rules", "hostel eligibility", "hostel fees",
            ])
        if is_procedural_query(query):
            markers.extend([
                "application", "application form", "admission procedure", "admission process",
                "submit", "submitted", "office", "warden", "principal",
                "documents required", "eligibility",
            ])
        if is_person_lookup_query(query):
            title = get_requested_person_title(query)
            if title:
                markers.append(title)
            markers.extend([
                "name designation", "no name designation", "staff", "faculty",
                "committee members", "office bearers", "department", "contact",
                "principal", "vice principal", "warden", "head of department",
                "hod", "coordinator", "secretary", "librarian", "chairperson",
            ])
        if is_staff_query(query):
            markers.extend([
                "teaching staff", "faculty", "teacher", "teachers", "professor",
                "lecturer", "assistant professor", "associate professor",
                "department of", "head", "director",
            ])
            dept = extract_staff_department_from_query(query)
            if dept:
                markers.extend(_dept_aliases(normalize_text(dept)))

        if all_docs:
            from .bm25_index import bm25_retrieve
            cand_docs, cand_metas, _ = bm25_retrieve(query, top_k=500)
            for doc, meta in zip(cand_docs, cand_metas):
                meta = meta or {}
                if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                    continue
                if not metadata_matches_where_filter(meta, where_filter):
                    continue
                d_norm = normalize_text(doc)
                score = 0.0
                if any(m in d_norm for m in markers):
                    score += 450.0
                if is_department_query(query):
                    score += department_relevance_score(doc)
                if is_course_query(query):
                    score += course_relevance_score(query, doc)
                if is_club_query(query) or is_cell_or_committee_query(query):
                    score += club_relevance_score(query, doc)
                if is_activity_query(query):
                    score += activity_relevance_score(query, doc)
                score += admission_evidence_score(query, doc)
                score += document_evidence_score(query, doc)
                score += role_evidence_score(query, doc)
                score += fee_evidence_score(query, doc)
                score += hostel_evidence_score(query, doc)
                score += hostel_relevance_score(query, doc, meta) * 100.0
                score += procedural_relevance_score(query, doc, meta) * 80.0
                score += person_lookup_relevance_score(query, doc, meta) * 120.0
                score += staff_relevance_score(query, doc, meta) * 2.0
                if is_website_links_query(query) and meta.get("source_type") == "website_links":
                    score += 2000.0
                score += metadata_boost_score(query, doc, meta)
                if score > 0:
                    matched.append((score, doc, meta))
        else:
            batch_size = 500
            offset = 0
            while True:
                kwargs: dict[str, Any] = {
                    "include": ["documents", "metadatas"],
                    "limit": batch_size,
                    "offset": offset,
                }
                if where_filter:
                    kwargs["where"] = where_filter

                result = collection.get(**kwargs)
                docs  = result.get("documents", [])
                metas = result.get("metadatas", [])
                if not docs:
                    break

                for doc, meta in zip(docs, metas):
                    meta = meta or {}
                    if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                        continue
                    d_norm = normalize_text(doc)
                    score = 0.0
                    if any(m in d_norm for m in markers):
                        score += 450.0
                    if is_department_query(query):
                        score += department_relevance_score(doc)
                    if is_course_query(query):
                        score += course_relevance_score(query, doc)
                    if is_club_query(query) or is_cell_or_committee_query(query):
                        score += club_relevance_score(query, doc)
                    if is_activity_query(query):
                        score += activity_relevance_score(query, doc)
                    score += admission_evidence_score(query, doc)
                    score += document_evidence_score(query, doc)
                    score += role_evidence_score(query, doc)
                    score += fee_evidence_score(query, doc)
                    score += hostel_evidence_score(query, doc)
                    score += hostel_relevance_score(query, doc, meta) * 100.0
                    score += procedural_relevance_score(query, doc, meta) * 80.0
                    score += person_lookup_relevance_score(query, doc, meta) * 120.0
                    score += staff_relevance_score(query, doc, meta) * 2.0
                    if is_website_links_query(query) and meta.get("source_type") == "website_links":
                        score += 2000.0
                    score += metadata_boost_score(query, doc, meta)
                    if score > 0:
                        matched.append((score, doc, meta))

                if len(docs) < batch_size:
                    break
                offset += batch_size

        matched.sort(key=lambda item: item[0], reverse=True)
        out_docs  = [item[1] for item in matched[:limit]]
        out_metas = [item[2] for item in matched[:limit]]
        # One-line explanation: Set default distance to None for special list keyword search to represent the lack of vector distance.
        out_dists = [None] * len(out_docs)
        debug_rag(f"special lexical candidates={len(out_docs)} limit={limit}")
        return out_docs, out_metas, out_dists
    except Exception as e:
        print(f"[EduBot] Special list fallback failed: {e}")
        return [], [], []



def vector_retrieve_chunks(
    query: str,
    top_k: int,
    where_filter: dict | None,
    use_personal_docs: bool = False,
) -> tuple[list[str], list[dict], list[float]]:
    try:
        # Embed the query AS GIVEN — the caller already passes the distilled
        # embedding query ("expand for recall, distill for ranking"). Re-running
        # expand_query() here re-pollutes it with keyword tails (e.g. "contact
        # phone email address principal ...") that drag the embedding off-topic
        # and push the genuinely relevant chunk out of the vector top-N. Keyword
        # recall is still handled separately by the BM25 path on the expanded query.
        focused_embedding_query = query
        debug_rag("VECTOR EMBEDDING QUERY:", focused_embedding_query[:200])
        query_embedding = encode_query(focused_embedding_query)
        n_results = max(top_k, RETRIEVAL_CANDIDATES)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            kwargs["where"] = where_filter
        result = collection.query(**kwargs)

        raw_docs  = result.get("documents",  [[]])[0]
        raw_metas = result.get("metadatas",  [[]])[0]
        raw_dists = result.get("distances",  [[]])[0]

        debug_rag("RAW RETRIEVAL DISTANCES:", raw_dists[:10])
        debug_rag("RAW METADATA:", raw_metas[:3])
        debug_rag("RAW DOCS:", [str(doc or "")[:240] for doc in raw_docs[:2]])

        docs: list[str]    = []
        metas: list[dict]  = []
        dists: list[float] = []

        for doc, meta, dist in zip(raw_docs, raw_metas, raw_dists):
            meta = meta or {}
            if metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                docs.append(doc)
                metas.append(meta)
                dists.append(dist)

        debug_rag(f"vector candidates={len(docs)} n_results={n_results}")
        if DEBUG_RAG:
            from .debug import debug_print_chunks
            debug_print_chunks(query, docs, metas, dists, title="RAW VECTOR RESULTS")
        return docs, metas, dists
    except Exception as e:
        print(f"[EduBot] Vector retrieval failed: {e}")
        return [], [], []


# Generic institutional / filler terms that do not discriminate between documents.
# A topic made up only of these (after dropping stopwords) is treated as no topic.
_GENERIC_TOPIC_TERMS = {
    "college", "institution", "institute", "campus", "school", "university",
    "organisation", "organization", "details", "detail", "information", "info",
    "overview", "summary", "profile", "description", "brief", "place", "it",
}
_TOPIC_STOPWORDS = {"the", "a", "an", "of", "our", "this", "that", "their", "its", "and", "for"}


def _is_generic_topic(topic: str | None) -> bool:
    """True when a candidate exact-topic carries no discriminating content words."""
    words = [w for w in normalize_text(topic or "").split() if w not in _TOPIC_STOPWORDS]
    if not words:
        return True
    return all(w in _GENERIC_TOPIC_TERMS for w in words)


def _is_college_history_query(query: str) -> bool:
    """Distinguish institutional history from History-department content."""
    q = normalize_text(query)
    if "college" not in q:
        return False
    return any(marker in q for marker in (
        "history of the college",
        "college history",
        "short history",
        "brief history",
        "origin of the college",
        "college founded",
        "college established",
    ))


def _has_college_history_evidence(doc: str, meta: dict | None) -> bool:
    """Reject literal 'history' matches that contain no college-history evidence."""
    meta = meta or {}
    source_url = str(meta.get("source_url") or "").lower()
    filename = normalize_text(str(meta.get("filename") or ""))
    haystack = normalize_text(
        f"{doc} {meta.get('title', '')} {meta.get('section_title', '')} {source_url}"
    )
    return (
        "/college/history" in source_url
        or "st anthony" in haystack
        or "st anthony s college" in haystack
        or ("about" in filename and "college" in haystack)
    )


# TODO: split
def rerank_results(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    limit: int,
) -> tuple[list[str], list[dict], list[float]]:
    """Fused lexical + vector scoring with domain-specific boosts."""
    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)
    # Drop generic/stopword-only topics (e.g. "the college" extracted from
    # "profile of the college") so they don't grant the +250 body-match boost to
    # every document mentioning "college".
    strict_exact_topic = (
        exact_topic
        if exact_topic
        and not _is_generic_topic(exact_topic)
        and not (is_contact_query(query) or is_attendance_query(query) or is_club_query(query))
        else None
    )

    is_contact  = is_contact_query(query)
    is_head     = is_head_query(query)
    # A head/person lookup that names a department ("head of department of chemistry")
    # must NOT be treated as a department-content query — otherwise the department
    # relevance penalty (-140) drops the person's profile chunk out of the results.
    is_dept     = is_department_query(query) and not is_course_query(query) and not is_head
    is_course   = is_course_query(query)
    is_club     = is_club_query(query)
    is_cell     = is_cell_or_committee_query(query)
    is_activity = is_activity_query(query)
    is_fee      = is_fee_query(query)
    is_app_fee  = is_application_fee_query(query)
    is_attend   = is_attendance_query(query)
    is_criteria = is_criteria_query(query)
    is_staff    = is_staff_query(query)
    is_toc_safe = "contents" not in normalize_text(query)

    scored: list[tuple[float, str, dict, float]] = []

    for doc, meta, dist in zip(docs, metas, dists):
        try:
            distance = float(dist)
        except Exception:
            distance = 999.0

        lexical      = keyword_score(query, doc)
        vector_score = max(0.0, 2.0 - distance) * 20.0
        meta_score   = metadata_boost_score(query, doc, meta)
        evidence_score = (
            admission_evidence_score(query, doc)
            + document_evidence_score(query, doc)
            + role_evidence_score(query, doc)
            + fee_evidence_score(query, doc)
            + hostel_evidence_score(query, doc)
            + hostel_relevance_score(query, doc, meta) * 120.0
            + procedural_relevance_score(query, doc, meta) * 90.0
            + person_lookup_relevance_score(query, doc, meta) * 140.0 # This line is already present in the original file.
            + staff_relevance_score(query, doc, meta)
        )
        intent_score = score_chunk_by_intent(query, doc, meta)
        final_score  = lexical + vector_score + meta_score + evidence_score + intent_score

        d_norm    = normalize_text(doc)
        body_norm = normalize_text(content_without_context_header(doc))

        if strict_exact_topic:
            if strict_exact_topic in body_norm:
                final_score += 250.0
            elif is_specific_query(query):
                final_score -= 180.0

        if is_contact:
            cs = contact_marker_score(doc)
            final_score += cs if cs > 0 else -100.0
        if is_head:
            final_score += 180.0 if has_head_marker_near_topic(doc, exact_topic) else -100.0
        if is_dept:
            ds = department_relevance_score(doc)
            final_score += ds if ds > 0 else -140.0
        if is_course:
            final_score += course_relevance_score(query, doc)
        if is_club or is_cell:
            final_score += club_relevance_score(query, doc)
        if is_activity:
            final_score += activity_relevance_score(query, doc)
        if is_fee:
            fs = fee_evidence_score(query, doc)
            final_score += fs if fs > 0 else -100.0
            if is_app_fee:
                final_score += 2000.0 if ("application fee" in d_norm or "application fees" in d_norm) else -140.0
            # A generic (non-hostel) fee question should not be dominated by the
            # hostel prospectus fee tables; demote hostel-scoped chunks here.
            if not is_hostel_query(query):
                scope_hay = normalize_text(
                    f"{(meta or {}).get('filename','')} "
                    f"{(meta or {}).get('section_title','')} "
                    f"{(meta or {}).get('source_pdf_filename','')}"
                )
                if "hostel" in scope_hay or "prospectus" in scope_hay:
                    final_score -= 400.0
        if is_attend:
            ars = attendance_relevance_score(doc)
            final_score += ars if ars > 0 else -180.0
            
        if is_website_links_query(query):
            if meta.get("source_type") == "website_links":
                final_score += 4000.0
        elif meta.get("source_type") == "website_links":
            # Demote raw navigation/link-dump chunks for non-link queries so web
            # nav boilerplate cannot crowd out real official content (paired with
            # the source_priority demotion in freshness.py).
            final_score -= 400.0

        if is_criteria:
            final_score += criteria_relevance_score(query, doc)
        if is_staff:
            ss = staff_relevance_score(query, doc, meta)
            final_score += ss if ss > 0 else -300.0
        if is_toc_safe and is_toc_candidate(doc, meta):
            final_score -= 1600.0

        if final_score > 0:
            scored.append((final_score, doc, meta or {}, distance))

        debug_rag(
            "score",
            f"final={final_score:.2f}",
            f"lexical={lexical:.2f}",
            f"vector={vector_score:.2f}",
            f"meta={meta_score:.2f}",
            f"evidence={evidence_score:.2f}",
            f"intent={intent_score:.2f}",
            f"file={(meta or {}).get('filename')}",
            f"page={(meta or {}).get('page')}",
            f"section={(meta or {}).get('section_title')}",
            f"toc={is_toc_candidate(doc, meta)}",
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    return (
        [item[1] for item in scored[:limit]],
        [item[2] for item in scored[:limit]],
        [item[3] for item in scored[:limit]],
    )


# KNOWLEDGE HIERARCHY: which document_type satisfies each query-intent category.
_CATEGORY_TO_DOCTYPE = {
    "admission": "prospectus",
    "academic_rules": "handbook",
    "hostel": "hostel",
}


def _combine_where(base: dict | None, extra: dict) -> dict:
    """AND a Tier-1 metadata constraint onto an existing where filter."""
    if not base:
        return extra
    return {"$and": [base, extra]}


def apply_knowledge_hierarchy(
    query: str,
    final_docs: list[str],
    final_metas: list[dict],
    final_dists: list[float | None],
    where_filter: dict | None,
    use_personal_docs: bool,
    embedding_query: str | None,
    top_k: int,
) -> tuple[list[str], list[dict], list[float | None]]:
    """
    Enforce the KNOWLEDGE HIERARCHY: when a query relates to a Tier 1 canonical
    source (Prospectus / Handbook / Hostel Prospectus), run a metadata-filtered
    retrieval restricted to that source and PREPEND its relevant chunks, so the
    canonical document is consulted first.

    Guard rails (so the rest of the 400-doc KB is never degraded):
    - Only activates when the query intent matches a Tier 1 category.
    - No-op when the current top result is already the matching Tier 1 source.
    - Only prepends Tier 1 chunks that actually CONTAIN the requested information
      (vector distance < MAX_DISTANCE or a real keyword match); otherwise the
      existing (lower-priority) results stand — matching the spec's "only use
      lower-priority documents if Tier 1 does not contain the requested info."
    """
    from .config import MAX_DISTANCE
    from .authority import query_authority_intent, authority_rank

    intent = query_authority_intent(query)
    categories = intent.get("categories") or set()
    if not categories:
        return final_docs, final_metas, final_dists

    # Already Tier-1-led for this intent? Leave it untouched.
    if final_metas and authority_rank(query, final_metas[0]) >= 2:
        return final_docs, final_metas, final_dists

    doctypes = sorted({
        _CATEGORY_TO_DOCTYPE[c] for c in categories if c in _CATEGORY_TO_DOCTYPE
    })
    if not doctypes:
        return final_docs, final_metas, final_dists

    tier1_where = _combine_where(where_filter, {"document_type": {"$in": doctypes}})
    emb_q = embedding_query or query

    try:
        v_docs, v_metas, v_dists = vector_retrieve_chunks(
            query=emb_q, top_k=30, where_filter=tier1_where,
            use_personal_docs=use_personal_docs,
        )
    except Exception:
        v_docs, v_metas, v_dists = [], [], []
    try:
        k_docs, k_metas, k_dists = keyword_retrieve_chunks(
            query=query, where_filter=tier1_where, limit=60,
            use_personal_docs=use_personal_docs,
        )
    except Exception:
        k_docs, k_metas, k_dists = [], [], []

    # Merge tier-1 candidates, keeping the best (smallest) known distance.
    merged: dict[str, tuple[str, dict, float | None]] = {}
    for doc, meta, dist in list(zip(v_docs, v_metas, v_dists)) + list(zip(k_docs, k_metas, k_dists)):
        key = candidate_dedupe_key(doc, meta)
        prev = merged.get(key)
        if prev is None or (prev[2] is None and dist is not None):
            merged[key] = (doc, meta, dist)
    if not merged:
        return final_docs, final_metas, final_dists

    cand_docs = [v[0] for v in merged.values()]
    cand_metas = [v[1] for v in merged.values()]
    cand_dists = [v[2] for v in merged.values()]

    r_docs, r_metas, r_dists = rerank_results(
        query, cand_docs, cand_metas, cand_dists, limit=10,
    )

    # "Contains the requested information" gate: on-topic by vector distance, or a
    # genuine keyword match in the chunk body.
    qualified: list[tuple[str, dict, float | None]] = []
    for doc, meta, dist in zip(r_docs, r_metas, r_dists):
        on_topic = (dist is not None and dist < MAX_DISTANCE) or keyword_score(query, doc) >= 30.0
        if on_topic and authority_rank(query, meta) >= 2:
            qualified.append((doc, meta, dist))
    if not qualified:
        return final_docs, final_metas, final_dists

    # Prepend up to 3 canonical chunks, then the existing results (deduped).
    prepend = qualified[:3]
    out_docs = [d for d, _m, _di in prepend]
    out_metas = [m for _d, m, _di in prepend]
    out_dists = [di for _d, _m, di in prepend]
    seen = {candidate_dedupe_key(d, m) for d, m in zip(out_docs, out_metas)}

    for doc, meta, dist in zip(final_docs, final_metas, final_dists):
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        out_docs.append(doc)
        out_metas.append(meta)
        out_dists.append(dist)

    return out_docs[:top_k], out_metas[:top_k], out_dists[:top_k]


# Programme codes that may have a DEDICATED faculty roster document — a file
# whose body literally reads "...Faculty Members teaching <CODE>..." (e.g.
# FP.pdf, "Profile of Faculty Members teaching MCA"). The marker must actually
# exist in the index for the override below to fire, so this list only widens
# which codes are CONSIDERED; it can never invent a roster.
_PROGRAMME_FACULTY_CODES = ("mca", "pgdca", "bca", "mba", "bba", "msw")


def _named_programme_for_faculty_query(query: str) -> str | None:
    """
    Return the programme code when the query is a faculty/staff question that
    names a specific programme — e.g. "who are the faculty of MCA" -> "mca".

    This is deliberately narrow: it only matches a whole-word programme CODE, so
    a department question ("faculty of computer science") does not trigger the
    programme-specific roster override.
    """
    if not is_staff_query(query):
        return None
    q = normalize_text(query)
    for code in _PROGRAMME_FACULTY_CODES:
        if re.search(rf"\b{re.escape(code)}\b", q):
            return code
    return None


def _is_program_faculty_roster(doc: str, programme: str) -> bool:
    """True for the dedicated 'Faculty Members teaching <programme>' roster."""
    body = normalize_text(content_without_context_header(doc))
    return f"faculty members teaching {programme}" in body


def _keep_with_program_roster(doc: str, meta: dict | None, programme: str) -> bool:
    """
    Decide whether a non-roster chunk may remain alongside the dedicated
    programme roster. Once the authoritative roster is found, the answer must not
    be contaminated by department-wide or college-wide faculty listings (which
    name staff who do not teach the programme). Keep only:
      - individual single-person profile documents (corroborate designations);
      - chunks that explicitly mention the programme code (programme-scoped
        context that is not itself a multi-person roster).
    """
    meta = meta or {}
    if "profile" in normalize_text(str(meta.get("filename", ""))):
        return True
    body = normalize_text(doc)
    # A multi-person roster (department/college-wide list) is never kept.
    if "name of the faculty" in body:
        return False
    if body.count("assistant professor") + body.count("associate professor") >= 3:
        return False
    if len(re.findall(r"\bprof\b", body)) >= 3:
        return False
    return bool(re.search(rf"\b{re.escape(programme)}\b", body))


def apply_program_faculty_authority(
    query: str,
    final_docs: list[str],
    final_metas: list[dict],
    final_dists: list[float | None],
    where_filter: dict | None,
    use_personal_docs: bool,
    top_k: int,
) -> tuple[list[str], list[dict], list[float | None]]:
    """
    A dedicated per-programme faculty roster (e.g. FP.pdf, "Profile of Faculty
    Members teaching MCA") is the authoritative answer to "who are the faculty of
    <programme>". These rosters are sparse name + profile-link tables that the
    cross-encoder scores near zero, so they are cut before display and the answer
    falls back to a generic, department-wide roster that names staff who do not
    teach the programme.

    When the query is a faculty/staff question that names such a programme, fetch
    the dedicated roster by its explicit document marker, PREPEND it, and drop
    department-wide rosters so they cannot contaminate the programme answer.

    No-op (existing behaviour preserved) whenever the query is not a
    programme-specific faculty question, or no dedicated roster exists in the
    index — so it can never degrade the rest of the knowledge base.
    """
    programme = _named_programme_for_faculty_query(query)
    if not programme:
        return final_docs, final_metas, final_dists

    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        from .bm25_index import _bm25_model

        if _bm25_model is None:
            load_bm25_index()
        all_docs, all_metas = get_all_documents_and_metas()
    except Exception:
        return final_docs, final_metas, final_dists

    roster: list[tuple[str, dict, float | None]] = []
    seen: set[str] = set()
    for doc, meta in zip(all_docs or [], all_metas or []):
        meta = meta or {}
        if not _is_program_faculty_roster(doc, programme):
            continue
        if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
            continue
        if not metadata_matches_where_filter(meta, where_filter):
            continue
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        roster.append((doc, meta, None))

    if not roster:
        return final_docs, final_metas, final_dists

    out_docs = [d for d, _m, _di in roster]
    out_metas = [m for _d, m, _di in roster]
    out_dists = [di for _d, _m, di in roster]

    for doc, meta, dist in zip(final_docs, final_metas, final_dists):
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        if not _keep_with_program_roster(doc, meta, programme):
            continue
        out_docs.append(doc)
        out_metas.append(meta)
        out_dists.append(dist)

    return out_docs[:top_k], out_metas[:top_k], out_dists[:top_k]


def _extract_exact_codes(query: str) -> list[str]:
    raw = re.findall(r"\b[A-Za-z]{2,}(?:[- ]?[A-Za-z]{1,4})?[- ]?\d{2,4}(?:\.\d+)?\b", str(query or ""))
    deduped: list[str] = []
    seen: set[str] = set()
    for code in raw:
        canonical = re.sub(r"[^a-z0-9]+", "", code.lower())
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        deduped.append(canonical)
    return deduped


def apply_exact_code_authority(
    query: str,
    final_docs: list[str],
    final_metas: list[dict],
    final_dists: list[float | None],
    where_filter: dict | None,
    use_personal_docs: bool,
    top_k: int,
) -> tuple[list[str], list[dict], list[float | None]]:
    """Prepend direct exact-code matches for literal course-code queries."""
    codes = _extract_exact_codes(query)
    if not codes:
        return final_docs, final_metas, final_dists

    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        from .bm25_index import _bm25_model

        if _bm25_model is None:
            load_bm25_index()
        all_docs, all_metas = get_all_documents_and_metas()
    except Exception:
        return final_docs, final_metas, final_dists

    matches: list[tuple[str, dict, float | None]] = []
    seen: set[str] = set()
    for doc, meta in zip(all_docs or [], all_metas or []):
        meta = meta or {}
        if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
            continue
        if not metadata_matches_where_filter(meta, where_filter):
            continue
        haystack = re.sub(
            r"[^a-z0-9]+", "",
            normalize_text(
                f"{meta.get('section_title', '')} {meta.get('filename', '')} {content_without_context_header(doc)}"
            ),
        )
        if not any(code in haystack for code in codes):
            continue
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        matches.append((doc, meta, None))

    if not matches:
        return final_docs, final_metas, final_dists

    out_docs = [doc for doc, _meta, _dist in matches[:3]]
    out_metas = [meta for _doc, meta, _dist in matches[:3]]
    out_dists = [dist for _doc, _meta, dist in matches[:3]]
    seen_keys = {candidate_dedupe_key(doc, meta) for doc, meta in zip(out_docs, out_metas)}
    for doc, meta, dist in zip(final_docs, final_metas, final_dists):
        key = candidate_dedupe_key(doc, meta)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out_docs.append(doc)
        out_metas.append(meta)
        out_dists.append(dist)
    return out_docs[:top_k], out_metas[:top_k], out_dists[:top_k]


def apply_department_roster_authority(
    query: str,
    final_docs: list[str],
    final_metas: list[dict],
    final_dists: list[float | None],
    where_filter: dict | None,
    use_personal_docs: bool,
    top_k: int,
) -> tuple[list[str], list[dict], list[float | None]]:
    """Prepend authoritative department roster/head chunks for staff queries."""
    if not (is_staff_query(query) or is_head_query(query)):
        return final_docs, final_metas, final_dists

    dept = extract_staff_department_from_query(query) or extract_department_from_query(query)
    wants_multi_department_heads = is_list_query(query) and "departments" in normalize_query(query) and (
        "heads" in normalize_query(query) or "hod" in normalize_query(query)
    )

    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        from .bm25_index import _bm25_model

        if _bm25_model is None:
            load_bm25_index()
        all_docs, all_metas = get_all_documents_and_metas()
    except Exception:
        return final_docs, final_metas, final_dists

    dept_aliases = _dept_aliases(dept) if dept else []
    matches: list[tuple[str, dict, float | None]] = []
    seen: set[str] = set()
    for doc, meta in zip(all_docs or [], all_metas or []):
        meta = meta or {}
        if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
            continue
        if not metadata_matches_where_filter(meta, where_filter):
            continue
        combined = normalize_text(
            f"{meta.get('filename', '')} {meta.get('section_title', '')} {content_without_context_header(doc)}"
        )
        if wants_multi_department_heads:
            if combined.count("department of") < 2 or "head :" not in combined:
                continue
        else:
            if not dept_aliases or not any(alias in combined for alias in dept_aliases):
                continue
            if "head :" not in combined and "head (ug)" not in combined and "director (pg)" not in combined:
                continue
            if is_list_query(query) and "teaching staff" not in combined:
                continue
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        matches.append((doc, meta, None))

    if not matches:
        return final_docs, final_metas, final_dists

    out_docs = [doc for doc, _meta, _dist in matches[:4]]
    out_metas = [meta for _doc, meta, _dist in matches[:4]]
    out_dists = [dist for _doc, _meta, dist in matches[:4]]
    seen_keys = {candidate_dedupe_key(doc, meta) for doc, meta in zip(out_docs, out_metas)}
    for doc, meta, dist in zip(final_docs, final_metas, final_dists):
        key = candidate_dedupe_key(doc, meta)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out_docs.append(doc)
        out_metas.append(meta)
        out_dists.append(dist)
    return out_docs[:top_k], out_metas[:top_k], out_dists[:top_k]


def _chunk_sort_key(meta: dict | None) -> tuple[str, int, int]:
    meta = meta or {}
    try:
        page = int(meta.get("page", 0))
    except Exception:
        page = 0
    try:
        chunk_index = int(meta.get("chunk_index", 0))
    except Exception:
        chunk_index = 0
    return str(meta.get("filename", "")), page, chunk_index


# TODO: split
def expand_with_related_chunks(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    where_filter: dict | None,
    use_personal_docs: bool = False,
) -> tuple[list[str], list[dict], list[float]]:
    if not docs:
        return docs, metas, dists

    include_page   = is_document_overview_query(query) or is_website_links_query(query)
    related_window = 10 if (is_department_query(query) or is_list_query(query) or is_staff_query(query)) else 1
    exact_topic    = extract_role_query(query).get("target") or extract_exact_topic(query)
    require_related_topic = (
        bool(exact_topic) and is_specific_query(query)
        and not (is_attendance_query(query) or is_head_query(query) or is_club_query(query))
    )

    if is_head_query(query):
        related_window = 2
    elif (is_department_query(query) and not is_course_query(query)) or is_list_query(query) or is_course_query(query) or is_staff_query(query):
        related_window = 8
    elif is_document_overview_query(query):
        include_page   = True
        related_window = 10

    merged: list[tuple[str, dict, float]] = []
    seen: set[str] = set()

    def _add(doc: str, meta: dict | None, dist: float) -> None:
        meta = meta or {}
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            return
        seen.add(key)
        merged.append((doc, meta, dist))

    for doc, meta, dist in zip(docs, metas, dists):
        _add(doc, meta, dist)

    fetched_filenames: set[str] = set()

    for meta in metas:
        meta = meta or {}
        filename = meta.get("filename")
        if not filename or filename in fetched_filenames:
            continue
        fetched_filenames.add(filename)

        try:
            page = int(meta.get("page", 0))
        except Exception:
            page = 0
        try:
            chunk_index = int(meta.get("chunk_index", -1))
        except Exception:
            chunk_index = -1

        try:
            result = collection.get(
                where={"filename": {"$eq": filename}},
                include=["documents", "metadatas"],
                limit=600,
            )
        except Exception as e:
            print(f"[EduBot] Related chunk fetch failed for {filename!r}: {e}")
            continue

        page_items: list[tuple[str, dict]] = []
        for related_doc, related_meta in zip(
            result.get("documents", []), result.get("metadatas", [])
        ):
            related_meta = related_meta or {}
            if not metadata_allows_query(related_meta, use_personal_docs=use_personal_docs):
                continue
            if require_related_topic and exact_topic not in normalize_text(
                content_without_context_header(related_doc)
            ):
                continue

            try:
                related_page = int(related_meta.get("page", 0))
            except Exception:
                related_page = 0
            try:
                related_chunk = int(related_meta.get("chunk_index", -1))
            except Exception:
                related_chunk = -1

            same_page     = page and related_page == page
            near_chunk    = chunk_index >= 0 and related_chunk >= 0 and abs(related_chunk - chunk_index) <= related_window
            forward_chunk = chunk_index >= 0 and related_chunk >= chunk_index and related_chunk <= chunk_index + related_window
            is_backward   = (
                chunk_index >= 0 and related_chunk < chunk_index
                and abs(related_chunk - chunk_index) <= related_window
            ) if is_head_query(query) else False

            if include_page and same_page:
                page_items.append((related_doc, related_meta))
            elif ((is_department_query(query) and not is_course_query(query)) or is_list_query(query)) and forward_chunk:
                page_items.append((related_doc, related_meta))
            elif (near_chunk or is_backward) and same_page:
                page_items.append((related_doc, related_meta))

        page_items.sort(key=lambda item: _chunk_sort_key(item[1]))
        for related_doc, related_meta in page_items:
            _add(related_doc, related_meta, 0.0)

        if len(merged) >= MAX_RELATED_CHUNKS:
            break

    merged = sorted(merged[:MAX_RELATED_CHUNKS], key=lambda item: _chunk_sort_key(item[1]))
    return [item[0] for item in merged], [item[1] for item in merged], [item[2] for item in merged]


def hybrid_retrieve(
    query: str,
    top_k: int = 20,
    where_filter: dict | None = None,
    use_personal_docs: bool = False,
) -> tuple[list[str], list[dict], list[float]]:
    from .bm25_index import bm25_retrieve
    bm25_docs, bm25_metas, bm25_scores = bm25_retrieve(query, top_k=top_k)
    vector_docs, vector_metas, vector_dists = vector_retrieve_chunks(
        query=query, top_k=top_k, where_filter=where_filter, use_personal_docs=use_personal_docs
    )

    from .config import METADATA_BOOST, DEBUG
    
    if DEBUG:
        print(f"[DEBUG] Vector search TOP_K: {len(vector_docs)} results")
        print(f"[DEBUG] BM25 TOP_K: {len(bm25_docs)} results")

    rrf_scores: dict[str, float] = {}
    docs_map: dict[str, str] = {}
    metas_map: dict[str, dict] = {}
    dists_map: dict[str, float | None] = {}

    for rank, (doc, meta, score) in enumerate(zip(bm25_docs, bm25_metas, bm25_scores)):
        key = candidate_dedupe_key(doc, meta)
        docs_map[key] = doc
        metas_map[key] = meta
        dists_map[key] = None
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank + 1.0)

    for rank, (doc, meta, dist) in enumerate(zip(vector_docs, vector_metas, vector_dists)):
        key = candidate_dedupe_key(doc, meta)
        if key not in docs_map:
            docs_map[key] = doc
            metas_map[key] = meta
        dists_map[key] = dist
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank + 1.0)

    if DEBUG:
        print(f"[DEBUG] RRF fused: {len(rrf_scores)} candidates")

    # Fix 3: apply post-RRF metadata boosting.
    # Only boost on DISCRIMINATING query terms. METADATA_BOOST is ~9x a typical
    # RRF contribution, so matching on filler/ultra-common words ("the", "college",
    # "office") boosts nearly every chunk and lets metadata word-overlap bury a
    # strong semantic match that simply lacks those words in its title/heading/
    # filename. Dropping stopwords and generic institutional terms keeps the boost
    # as a tie-breaker for meaningful terms instead of a ranking dominator.
    query_lower = query.lower()
    query_terms = [
        t for t in query_lower.split()
        if len(t) > 2 and t not in _TOPIC_STOPWORDS and t not in _GENERIC_TOPIC_TERMS
    ]
    matched_fields = []

    for key, score in rrf_scores.items():
        meta = metas_map[key]
        title = str(meta.get("title") or "").lower()
        heading = str(meta.get("heading") or "").lower()
        filename = str(meta.get("filename") or "").lower()
        
        matches = []
        for term in query_terms:
            if term in title:
                matches.append("title")
            if term in heading:
                matches.append("heading")
            if term in filename:
                matches.append("filename")
        
        if matches:
            rrf_scores[key] += METADATA_BOOST
            matched_fields.extend(matches)

    # KNOWLEDGE HIERARCHY recall bump: nudge Tier 1 canonical sources (Prospectus
    # / Handbook / Hostel Prospectus) when the query relates to their topics, so
    # they are not cut before the cross-encoder sees them. Scaled into RRF units
    # (METADATA_BOOST-sized) — a tie-breaker for recall, not a relevance override.
    try:
        from .authority import authority_rank
        for key in rrf_scores:
            tier = authority_rank(query, metas_map[key])
            if tier >= 2:
                rrf_scores[key] += METADATA_BOOST
            elif tier == 1:
                rrf_scores[key] += METADATA_BOOST * 0.25
    except Exception:
        pass

    if DEBUG:
        if matched_fields:
            print(f"[DEBUG] Metadata boost applied: yes, matched fields: {set(matched_fields)}")
        else:
            print("[DEBUG] Metadata boost applied: no")

    ranked = sorted([(score, key) for key, score in rrf_scores.items()], reverse=True)
    selected_keys = [key for _, key in ranked[:top_k]]
    
    return (
        [docs_map[k] for k in selected_keys],
        [metas_map[k] for k in selected_keys],
        [dists_map[k] for k in selected_keys]
    )

# TODO: split
def retrieve_chunks(
    query: str,
    top_k: int,
    where_filter: dict | None,
    use_personal_docs: bool = False,
    embedding_query: str | None = None,
    original_query: str | None = None,
) -> tuple[list[str], list[dict], list[float]]:
    from .config import DEBUG, RERANKER_INPUT_K, RERANKER_OUTPUT_K, KEYWORD_CANDIDATES, RETRIEVAL_CANDIDATES, RERANK_TOP_N
    from .cache import get_cached_retrieval, set_cached_retrieval, retrieval_scope_label
    from embeddings import EMBEDDING_MODEL, prefix_query_for_search

    orig_q = original_query or query
    expanded_q = embedding_query or query
    
    if DEBUG:
        print(f"[DEBUG] Original query: {orig_q}")
        print(f"[DEBUG] Expanded query: {expanded_q}")
        print(f"[DEBUG] BGE prefix applied: {prefix_query_for_search(expanded_q)}")

    # Fold the retrieval SCOPE into the cache key so a personal-docs or
    # department/year/document_type-filtered query can never be served another
    # scope's cached chunks (default official+unfiltered → stable shared label).
    scope_label = retrieval_scope_label(where_filter, use_personal_docs)
    # The same expanded BM25 query can be paired with different focused semantic
    # queries. Include the semantic representation in the cache identity so a
    # cached result can never bypass updated entity/semester/follow-up handling.
    semantic_signature = hashlib.sha256(
        normalize_query(expanded_q).encode("utf-8")
    ).hexdigest()[:16]
    intent_label = (
        f"topk_{top_k}_model_{EMBEDDING_MODEL}_scope_{scope_label}"
        f"_semantic_{semantic_signature}"
    )

    cached_results = get_cached_retrieval(query, intent_label)
    if cached_results is not None:
        if len(cached_results) > 0:
            cached_docs = [r["doc"] for r in cached_results]
            cached_metas = [r["meta"] for r in cached_results]
            cached_dists = [r["dist"] for r in cached_results]
            if DEBUG:
                print(f"[DEBUG] Layer 2 Retrieval Cache HIT for query: {query!r}")
                print(f"[DEBUG] Final chunks sent to LLM: {len(cached_docs)} chunks")
                print(f"[DEBUG] Sources: {[(m.get('filename'), m.get('page')) for m in cached_metas]}")
            return cached_docs, cached_metas, cached_dists
        else:
            if DEBUG:
                print(f"[DEBUG] Layer 2 Retrieval Cache returned zero chunks (miss).")

    if is_list_query(query):
        target_top_k = max(top_k, 8)
    else:
        target_top_k = top_k
    keyword_limit = max(KEYWORD_CANDIDATES, 150)

    keyword_docs, keyword_metas, keyword_dists = keyword_retrieve_chunks(
        query=query,
        where_filter=where_filter,
        limit=keyword_limit,
        use_personal_docs=use_personal_docs,
    )
    _embed_q = embedding_query or query
    vector_docs, vector_metas, vector_dists = hybrid_retrieve(
        query=_embed_q,
        top_k=max(100, RETRIEVAL_CANDIDATES),
        where_filter=where_filter,
        use_personal_docs=use_personal_docs,
    )
    fallback_docs, fallback_metas, fallback_dists = special_list_keyword_retrieve(
        query=query,
        where_filter=where_filter,
        use_personal_docs=use_personal_docs,
        limit=60,
    )

    combined = (
        list(zip(fallback_docs, fallback_metas, fallback_dists))
        + list(zip(keyword_docs, keyword_metas, keyword_dists))
        + list(zip(vector_docs, vector_metas, vector_dists))
    )

    merged_docs:  list[str]   = []
    merged_metas: list[dict]  = []
    merged_dists: list[float | None] = []

    key_to_index: dict[str, int] = {}
    for doc, meta, dist in combined:
        meta = meta or {}
        key = candidate_dedupe_key(doc, meta)
        if key not in key_to_index:
            key_to_index[key] = len(merged_docs)
            merged_docs.append(doc)
            merged_metas.append(meta)
            merged_dists.append(dist)
        else:
            idx = key_to_index[key]
            if merged_dists[idx] is None and dist is not None:
                merged_dists[idx] = dist

    debug_rag(
        "merged candidates",
        f"fallback={len(fallback_docs)}",
        f"keyword={len(keyword_docs)}",
        f"vector={len(vector_docs)}",
        f"merged={len(merged_docs)}",
    )

    local_limit = 40 if is_list_query(query) else max(RERANK_TOP_N, target_top_k * 4)
    selection_query = embedding_query or query
    local_docs, local_metas, local_dists = rerank_results(
        selection_query, merged_docs, merged_metas, merged_dists, local_limit,
    )

    if is_person_lookup_query(query):
        person_ordered = sorted(
            zip(local_docs, local_metas, local_dists),
            key=lambda item: (
                5000.0 if context_has_likely_person_name_for_title(query, item[0]) else 0.0
            )
            + (
                3000.0
                if is_hostel_query(query)
                and context_has_likely_person_name_for_title(query, item[0])
                and (
                    "hostel" in normalize_text(str((item[1] or {}).get("filename", "")))
                    or "hostel" in normalize_text(str((item[1] or {}).get("section_title", "")))
                    or "hostel" in normalize_text(str((item[1] or {}).get("source_pdf_filename", "")))
                )
                else 0.0
            )
            + (1500.0 if "administration" in normalize_text(item[0]) else 0.0)
            + person_lookup_relevance_score(query, item[0], item[1]) * 400.0
            + role_evidence_score(query, item[0])
            + metadata_boost_score(query, item[0], item[1]),
            reverse=True,
        )
        local_docs  = [item[0] for item in person_ordered]
        local_metas = [item[1] for item in person_ordered]
        local_dists = [item[2] for item in person_ordered]

    admission_category = str(classify_admission_query(query).get("category") or "")
    use_local_evidence_order = admission_category in {
        "admission_process", "admission_dates", "admission_form", "eligibility",
        "personal_eligibility", "documents", "fees", "merit_selection",
        "reservation", "hostel_admission", "contact", "role_person", "courses",
    } or is_head_query(query)

    # Build the cross-encoder input as the stage-1 top-K AUGMENTED with the
    # strongest pure-vector matches. The stage-1 scorer is cheap lexical fusion
    # and can rank a semantically-strong chunk (high vector similarity, few
    # literal keyword hits) below the RERANKER_INPUT_K cutoff — so the accurate
    # cross-encoder never sees it. Guaranteeing the best-by-distance candidates a
    # slot lets the cross-encoder judge them. Output size is unchanged.
    rerank_input = list(zip(local_docs[:RERANKER_INPUT_K],
                            local_metas[:RERANKER_INPUT_K],
                            local_dists[:RERANKER_INPUT_K]))
    _seen_rerank = {candidate_dedupe_key(d, m) for d, m, _ in rerank_input}
    _vector_candidates = sorted(
        (
            (d, m, di)
            for d, m, di in zip(merged_docs, merged_metas, merged_dists)
            if di is not None and di < 999.0
        ),
        key=lambda item: item[2],
    )
    for d, m, di in _vector_candidates[:RERANKER_INPUT_K]:
        k = candidate_dedupe_key(d, m)
        if k not in _seen_rerank:
            rerank_input.append((d, m, di))
            _seen_rerank.add(k)

    if DEBUG:
        print(f"[DEBUG] Reranker input: {len(rerank_input)} candidates")

    if not rerank_input:
        final_docs, final_metas, final_dists = [], [], []
        final_scores = []
    else:
        from reranker import rerank_chunks_with_scores
        _rerank_q = embedding_query or original_query or query
        # Returning a few extra semantic candidates costs no additional model
        # inference (the reranker already scores the full input) and prevents a
        # relevant source just below the display top-K from being lost before
        # related-chunk expansion.
        _initial_rerank_top_n = min(
            len(rerank_input),
            max(RERANKER_OUTPUT_K, target_top_k * 3),
        )
        final_docs, final_metas, final_dists, final_scores = rerank_chunks_with_scores(
            query=_rerank_q,
            docs=[item[0] for item in rerank_input],
            metas=[item[1] for item in rerank_input],
            dists=[item[2] for item in rerank_input],
            top_n=_initial_rerank_top_n,
        )

    if DEBUG and final_docs:
        print(f"[DEBUG] Reranker scores: {list(zip([m.get('filename') for m in final_metas], final_scores))}")

    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)
    strict_exact_topic = (
        exact_topic
        if exact_topic and not (is_contact_query(query) or is_attendance_query(query) or is_club_query(query))
        else None
    )

    if strict_exact_topic and is_specific_query(query):
        topic_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if strict_exact_topic in normalize_text(content_without_context_header(doc))
        ]
        if len(topic_filtered) >= min(target_top_k, max(3, len(final_docs) // 2)):
            final_docs, final_metas, final_dists = map(list, zip(*topic_filtered))  # type: ignore[assignment]

    if is_head_query(query):
        head_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if has_head_marker_near_topic(doc, exact_topic) or role_evidence_score(query, doc) >= 450.0
        ]
        if len(head_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            final_docs  = [item[0] for item in head_filtered]
            final_metas = [item[1] for item in head_filtered]
            final_dists = [item[2] for item in head_filtered]

    if is_attendance_query(query):
        att_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if attendance_relevance_score(doc) >= 300.0
        ]
        if len(att_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            final_docs  = [item[0] for item in att_filtered]
            final_metas = [item[1] for item in att_filtered]
            final_dists = [item[2] for item in att_filtered]

    if is_website_links_query(query):
        link_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if meta.get("source_type") == "website_links"
        ]
        if link_filtered:
            final_docs, final_metas, final_dists = map(list, zip(*link_filtered))

    if is_fee_query(query):
        fee_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if fee_evidence_score(query, doc) >= 250.0
        ]
        if is_application_fee_query(query):
            app_fee_filtered = [
                (doc, meta, dist) for doc, meta, dist in fee_filtered
                if "application fee" in normalize_text(doc) or "application fees" in normalize_text(doc)
            ]
            if app_fee_filtered:
                fee_filtered = app_fee_filtered
        if len(fee_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            fee_filtered.sort(key=lambda item: fee_evidence_score(query, item[0]), reverse=True)
            final_docs  = [item[0] for item in fee_filtered]
            final_metas = [item[1] for item in fee_filtered]
            final_dists = [item[2] for item in fee_filtered]

    if is_department_query(query) and not is_course_query(query):
        section_dept_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if "section departments" in normalize_text(doc)
        ]
        dept_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if department_relevance_score(doc) >= 250.0
        ]
        if len(section_dept_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            final_docs  = [item[0] for item in section_dept_filtered]
            final_metas = [item[1] for item in section_dept_filtered]
            final_dists = [item[2] for item in section_dept_filtered]
        elif len(dept_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            final_docs  = [item[0] for item in dept_filtered]
            final_metas = [item[1] for item in dept_filtered]
            final_dists = [item[2] for item in dept_filtered]

    if is_contact_query(query) and not is_person_lookup_query(query):
        contact_filtered = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if contact_marker_score(doc) > 0
        ]
        contact_filtered.sort(key=lambda item: contact_marker_score(item[0]), reverse=True)
        if len(contact_filtered) >= min(target_top_k, max(2, len(final_docs) // 2)):
            if contact_marker_score(contact_filtered[0][0]) >= 1500:
                contact_filtered = contact_filtered[:1]
            final_docs  = [item[0] for item in contact_filtered]
            final_metas = [item[1] for item in contact_filtered]
            final_dists = [item[2] for item in contact_filtered]

    if is_criteria_query(query):
        heading = _criteria_heading_for_query(query)
        if heading:
            criteria_filtered = [
                (doc, meta, dist)
                for doc, meta, dist in zip(final_docs, final_metas, final_dists)
                if heading in normalize_text(doc)
            ]
            if criteria_filtered:
                final_docs  = [item[0] for item in criteria_filtered]
                final_metas = [item[1] for item in criteria_filtered]
                final_dists = [item[2] for item in criteria_filtered]

    _skip_expand = (
        is_course_query(query)
        and not is_list_query(query)
        and not is_postgraduate_course_query(query)
        and not is_certificate_course_query(query)
    )
    if is_head_query(query):
        _skip_expand = True
    if use_local_evidence_order:
        _skip_expand = _skip_expand or not is_list_query(query)
    if not _skip_expand:
        final_docs, final_metas, final_dists = expand_with_related_chunks(
            query=query,
            docs=final_docs,
            metas=final_metas,
            dists=final_dists,
            where_filter=where_filter,
            use_personal_docs=use_personal_docs,
        )
        rerank_limit = max(target_top_k * 3, 20 if is_list_query(query) else target_top_k)
        # Related-chunk expansion must not replace the semantic cross-encoder
        # ranking with literal keyword ordering. That caused queries such as
        # "short history of the college" to discard the correct college-history
        # page in favour of unrelated books containing "A Short History".
        # Re-run the same semantic reranker over the expanded candidate set.
        if final_docs:
            from reranker import rerank_chunks_with_scores

            _expanded_rerank_q = embedding_query or original_query or query
            final_docs, final_metas, final_dists, _expanded_scores = rerank_chunks_with_scores(
                query=_expanded_rerank_q,
                docs=final_docs,
                metas=final_metas,
                dists=final_dists,
                top_n=rerank_limit,
            )
            if _is_college_history_query(orig_q):
                grounded_history = [
                    (doc, meta, dist, score)
                    for doc, meta, dist, score in zip(
                        final_docs, final_metas, final_dists, _expanded_scores
                    )
                    if _has_college_history_evidence(doc, meta)
                ]
                if grounded_history:
                    final_docs = [item[0] for item in grounded_history]
                    final_metas = [item[1] for item in grounded_history]
                    final_dists = [item[2] for item in grounded_history]
                    _expanded_scores = [item[3] for item in grounded_history]

    if is_person_lookup_query(query):
        ordered = sorted(
            zip(final_docs, final_metas, final_dists),
            key=lambda item: (
                person_lookup_relevance_score(query, item[0], item[1]) * 300.0
                + role_evidence_score(query, item[0])
                + metadata_boost_score(query, item[0], item[1])
            ),
            reverse=True,
        )
        final_docs  = [item[0] for item in ordered]
        final_metas = [item[1] for item in ordered]
        final_dists = [item[2] for item in ordered]

    if (is_hostel_query(query) or is_procedural_query(query)) and not is_fee_query(query) and not is_person_lookup_query(query):
        ordered = sorted(
            zip(final_docs, final_metas, final_dists),
            key=lambda item: (
                hostel_relevance_score(query, item[0], item[1]) * 120.0
                + procedural_relevance_score(query, item[0], item[1]) * 90.0
                + hostel_evidence_score(query, item[0])
                + admission_evidence_score(query, item[0])
                + metadata_boost_score(query, item[0], item[1])
            ),
            reverse=True,
        )
        final_docs  = [item[0] for item in ordered]
        final_metas = [item[1] for item in ordered]
        final_dists = [item[2] for item in ordered]

    # Constraint-aware precision gate for curriculum requests.  Run after
    # related-chunk expansion/reranking so a correct neighbouring syllabus chunk
    # can enter the set, but before freshness/authority/truncation.  Unlike a
    # metadata filter this checks the actual evidence and therefore works with
    # older chunks whose programme/semester metadata is incomplete.
    if _is_curriculum_request(orig_q):
        constrained = [
            (doc, meta, dist)
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
            if _curriculum_evidence_matches(orig_q, doc, meta)
        ]
        if constrained:
            final_docs = [item[0] for item in constrained]
            final_metas = [item[1] for item in constrained]
            final_dists = [item[2] for item in constrained]
        else:
            # A curriculum query with explicit constraints but no matching
            # curriculum evidence must not fall through to profiles/admissions.
            constraints = extract_query_constraints(orig_q)
            if any(constraints.get(key) for key in ("programme", "department", "semester")):
                final_docs, final_metas, final_dists = [], [], []

    try:
        items = list(zip(final_docs, final_metas, final_dists))
        ranked_items = freshness_rank_items(query, items)
        # Deterministically drop superseded older versions of the same policy
        # (audit §2.1) before context is built, so conflict resolution never
        # rests on crawl-timestamp tie-breaks or the LLM picking a version.
        before = len(ranked_items)
        ranked_items = drop_superseded_duplicates(ranked_items)
        if len(ranked_items) < before:
            debug_rag(f"dropped {before - len(ranked_items)} superseded duplicate chunk(s)")
        final_docs, final_metas, final_dists = map(list, zip(*ranked_items)) if ranked_items else ([], [], [])
    except Exception as e:
        debug_rag("freshness_rank_items failed; falling back to existing order", e)

    # For explicitly current/present role-holder questions, an older table that
    # merely labels someone "Principal" must not override a newer succession or
    # current-tenure statement. Narrow only when such explicit evidence exists;
    # otherwise preserve the normal person-lookup fallback behaviour.
    current_role_items = [
        (doc, meta, dist)
        for doc, meta, dist in zip(final_docs, final_metas, final_dists)
        if current_role_evidence_score(orig_q, doc) > 0
    ]
    if current_role_items:
        # The succession sentence may abbreviate the person (for example,
        # "Fr. Arcadius") while another current official document contains the
        # full name. Pull only same-person, same-role corroboration so the answer
        # can use the fullest indexed name without reintroducing older holders.
        role = normalize_text(str(extract_role_query(orig_q).get("role") or ""))
        dated_names = [
            (int(match.group(2)), match.group(1).lower())
            for doc, _meta, _dist in current_role_items
            for match in re.finditer(
                rf"\b(?:Dr\.?|Fr\.?|Br\.?|Sr\.?)\s+([A-Z][A-Za-z'-]+)\b"
                rf".{{0,100}}?took over as (?:the )?\d+(?:st|nd|rd|th) {re.escape(role)}"
                r".{0,80}?\b(20\d{2}|19\d{2})\b",
                doc,
                flags=re.IGNORECASE,
            )
        ]
        newest_year = max((year for year, _name in dated_names), default=0)
        first_names = {name for year, name in dated_names if year == newest_year}
        seen = {
            candidate_dedupe_key(doc, meta)
            for doc, meta, _dist in current_role_items
        }
        for first_name in sorted(first_names):
            from .bm25_index import bm25_retrieve

            corroborating_docs, corroborating_metas, _bm25_scores = bm25_retrieve(
                first_name,
                top_k=40,
            )
            corroborating_dists = [None] * len(corroborating_docs)
            for doc, meta, dist in zip(corroborating_docs, corroborating_metas, corroborating_dists):
                if not metadata_allows_query(meta, use_personal_docs=use_personal_docs):
                    continue
                if not metadata_matches_where_filter(meta, where_filter):
                    continue
                norm = normalize_text(doc)
                if not role or first_name not in norm or role not in norm:
                    continue
                if not re.search(
                    rf"\b{re.escape(first_name)}\b.{{0,120}}\b{re.escape(role)}\b|"
                    rf"\b{re.escape(role)}\b.{{0,120}}\b{re.escape(first_name)}\b",
                    norm,
                ):
                    continue
                key = candidate_dedupe_key(doc, meta)
                if key in seen:
                    continue
                seen.add(key)
                current_role_items.append((doc, meta, dist))
                if len(current_role_items) >= 3:
                    break
            if len(current_role_items) >= 3:
                break

        final_docs = [item[0] for item in current_role_items]
        final_metas = [item[1] for item in current_role_items]
        final_dists = [item[2] for item in current_role_items]

    # KNOWLEDGE HIERARCHY: consult Tier 1 canonical sources first (metadata-filtered
    # retrieval + prepend), gated so lower-priority docs still answer when Tier 1
    # lacks the info. Wrapped so any failure degrades to the existing order.
    try:
        final_docs, final_metas, final_dists = apply_knowledge_hierarchy(
            query=query,
            final_docs=final_docs,
            final_metas=final_metas,
            final_dists=final_dists,
            where_filter=where_filter,
            use_personal_docs=use_personal_docs,
            embedding_query=embedding_query,
            top_k=max(target_top_k, len(final_docs)),
        )
    except Exception as e:
        debug_rag("apply_knowledge_hierarchy failed; falling back to existing order", e)

    try:
        final_docs, final_metas, final_dists = apply_department_roster_authority(
            query=orig_q,
            final_docs=final_docs,
            final_metas=final_metas,
            final_dists=final_dists,
            where_filter=where_filter,
            use_personal_docs=use_personal_docs,
            top_k=max(target_top_k, len(final_docs)),
        )
    except Exception as e:
        debug_rag("apply_department_roster_authority failed; falling back to existing order", e)

    # PROGRAMME FACULTY: a "who are the faculty of <programme>" question must be
    # answered from the dedicated programme roster (e.g. FP.pdf for MCA), not a
    # department-wide staff list. Wrapped so any failure degrades to the existing
    # order.
    try:
        final_docs, final_metas, final_dists = apply_program_faculty_authority(
            query=orig_q,
            final_docs=final_docs,
            final_metas=final_metas,
            final_dists=final_dists,
            where_filter=where_filter,
            use_personal_docs=use_personal_docs,
            top_k=max(target_top_k, len(final_docs)),
        )
    except Exception as e:
        debug_rag("apply_program_faculty_authority failed; falling back to existing order", e)

    try:
        final_docs, final_metas, final_dists = apply_exact_code_authority(
            query=orig_q,
            final_docs=final_docs,
            final_metas=final_metas,
            final_dists=final_dists,
            where_filter=where_filter,
            use_personal_docs=use_personal_docs,
            top_k=max(target_top_k, len(final_docs)),
        )
    except Exception as e:
        debug_rag("apply_exact_code_authority failed; falling back to existing order", e)

    if len(final_docs) > target_top_k:
        final_docs  = final_docs[:target_top_k]
        final_metas = final_metas[:target_top_k]
        final_dists = final_dists[:target_top_k]

    debug_rag(f"final selected chunks={len(final_docs)}")
    if DEBUG_RAG:
        from .debug import debug_print_chunks
        debug_print_chunks(query, final_docs, final_metas, final_dists, title="FINAL SELECTED CONTEXT CHUNKS")
        for doc, meta, dist in zip(final_docs, final_metas, final_dists):
            meta = meta or {}
            debug_rag(
                "selected",
                f"file={meta.get('filename')!r}",
                f"page={meta.get('page')}",
                f"chunk={meta.get('chunk_index')}",
                f"distance={dist:.4f}" if dist is not None else "distance=None",
                f"section={meta.get('section_title')!r}",
                f"toc={is_toc_candidate(doc, meta)}",
                f"preview={clean_text(doc)[:180]!r}",
            )

    if DEBUG:
        print(f"[DEBUG] Final chunks sent to LLM: {len(final_docs)} chunks")
        print(f"[DEBUG] Sources: {[(m.get('filename'), m.get('page')) for m in final_metas]}")

    if len(final_docs) > 0:
        cache_data = [
            {"doc": d, "meta": m, "dist": dst}
            for d, m, dst in zip(final_docs, final_metas, final_dists)
        ]
        set_cached_retrieval(query, intent_label, cache_data)

    return final_docs, final_metas, final_dists


def person_lookup_fallback_context(
    query: str,
    where_filter: dict | None,
    use_personal_docs: bool = False,
) -> tuple[str, list[dict]]:
    if not is_person_lookup_query(query):
        return "", []

    title = get_requested_person_title(query)
    title_terms = [
        title,
        "warden",
        "hostel warden",
        "girls hostel warden",
        "boys hostel warden",
        "superintendent",
        "hostel superintendent",
        "matron",
        "rector",
        "in charge",
        "hostel in charge",
    ]
    fallback_query = normalize_query(expand_person_lookup_query(" ".join(
        part for part in [query, *title_terms] if part
    )))

    keyword_docs, keyword_metas, keyword_dists = keyword_retrieve_chunks(
        query=fallback_query,
        where_filter=where_filter,
        limit=100,
        use_personal_docs=use_personal_docs,
    )
    special_docs, special_metas, special_dists = special_list_keyword_retrieve(
        query=fallback_query,
        where_filter=where_filter,
        use_personal_docs=use_personal_docs,
        limit=100,
    )

    combined = list(zip(special_docs, special_metas, special_dists)) + list(zip(keyword_docs, keyword_metas, keyword_dists))
    merged_docs: list[str] = []
    merged_metas: list[dict] = []
    merged_dists: list[float] = []
    seen: set[str] = set()
    for doc, meta, dist in combined:
        meta = meta or {}
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        merged_docs.append(doc)
        merged_metas.append(meta)
        merged_dists.append(dist)

    if not merged_docs:
        return "", []

    ranked_docs, ranked_metas, ranked_dists = rerank_results(
        query=query,
        docs=merged_docs,
        metas=merged_metas,
        dists=merged_dists,
        limit=30,
    )
    if DEBUG_RAG:
        from .debug import debug_print_chunks
        debug_print_chunks(query, ranked_docs, ranked_metas, ranked_dists, title="PERSON LOOKUP FALLBACK CHUNKS")

    fallback_context, fallback_sources = build_context(query, ranked_docs[:8], ranked_metas[:8], ranked_dists[:8])
    valid_sources = [
        source for source in fallback_sources
        if context_has_likely_person_name_for_title(query, str(source.get("text") or ""))
    ]
    if not valid_sources or not context_has_likely_person_name_for_title(query, fallback_context):
        return "", []

    filtered_context = "\n\n---\n\n".join(
        (
            f"[Source {source.get('id')} | File: {source.get('file')} | "
            f"Page: {source.get('page_label') or source.get('page')} | "
            f"Section: {source.get('section_title')} | Chunk: {source.get('chunk_index')}]\n"
            f"{source.get('text') or ''}"
        )
        for source in valid_sources
    )
    return filtered_context, valid_sources


def filter_staff_docs(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
) -> tuple[list[str], list[dict], list[float]]:
    if not is_staff_query(query):
        return docs, metas, dists

    dept = extract_department_from_query(query)
    dept_aliases = _dept_aliases(dept) if dept else []

    filtered_docs: list[str] = []
    filtered_metas: list[dict] = []
    filtered_dists: list[float] = []

    for doc, meta, dist in zip(docs, metas, dists):
        if chunk_looks_like_course_only(doc):
            continue
        if not chunk_has_staff_evidence(doc):
            continue
        if is_list_query(query):
            roster_text = normalize_text(
                f"{(meta or {}).get('section_title', '')} {doc}"
            )
            has_roster = (
                bool(re.search(r"(?<!non )\bteaching staff\b", roster_text))
                or "faculty members" in roster_text
                or "department faculty" in roster_text
                or ("name" in roster_text and "designation" in roster_text)
            )
            if not has_roster:
                continue
        if dept_aliases:
            doc_l = normalize_text(
                f"{(meta or {}).get('filename', '')} {(meta or {}).get('section_title', '')} {doc}"
            )
            if not any(alias in doc_l for alias in dept_aliases):
                continue
        filtered_docs.append(doc)
        filtered_metas.append(meta)
        filtered_dists.append(dist)

    return filtered_docs, filtered_metas, filtered_dists
