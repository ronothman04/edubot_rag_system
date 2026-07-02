"""
rag/authority.py

Single source of truth for EduBot's KNOWLEDGE HIERARCHY (document priority).

The four canonical "Tier 1" sources — Prospectus 2026, College Handbook, Boys
Hostel Prospectus, Girls Hostel Prospectus — are the highest authority in the
knowledge base. Everything here is PURE and additive:

- `classify_document(meta)` derives the authority metadata for a chunk from its
  filename (or any authority fields already present). It is used BOTH at ingest
  time (to stamp metadata) AND at query time (so it works on the existing index
  with no re-ingestion).
- `query_authority_intent(query)` maps a user question to the authority
  categories it relates to (admission / academic_rules / hostel + boys/girls).
- `authority_rank(query, meta)` / `authority_score_boost(query, meta)` are the
  signals the ranking pipeline uses to PREFER Tier 1 documents within a close
  relevance band. They are tie-breakers, never relevance overrides — a
  lower-priority document still surfaces when the Tier 1 docs do not contain the
  requested information.
"""

from __future__ import annotations

import re
from typing import Any

# Authority categories used to match a query's intent against a document.
CAT_ADMISSION = "admission"
CAT_ACADEMIC_RULES = "academic_rules"
CAT_HOSTEL = "hostel"

# Tier 1 authority score / level (matches the spec example values).
TIER1_AUTHORITY_SCORE = 100
TIER1_PRIORITY_LEVEL = "highest"

# Defaults for non-Tier-1 (standard) documents.
STANDARD_AUTHORITY_SCORE = 50
STANDARD_PRIORITY_LEVEL = "standard"


def _meta_filename(meta: dict | None) -> str:
    meta = meta or {}
    for key in ("filename", "source_filename", "source_pdf_filename", "title"):
        value = str(meta.get(key) or "").strip()
        if value and value.lower() not in {"unknown", "general", "none", "null"}:
            return value
    return ""


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


# Ordered hierarchy. Order matters: hostel patterns are checked BEFORE the
# generic prospectus pattern because the hostel files also contain "prospectus".
# Each entry: (predicate(normalized_name) -> bool, document_type, category,
#              hostel_type, display_name).
_HIERARCHY: list[tuple] = [
    (
        lambda n: "boys" in n and "hostel" in n,
        "hostel", CAT_HOSTEL, "boys", "Boys Hostel Prospectus",
    ),
    (
        lambda n: "girls" in n and "hostel" in n,
        "hostel", CAT_HOSTEL, "girls", "Girls Hostel Prospectus",
    ),
    (
        lambda n: "handbook" in n,
        "handbook", CAT_ACADEMIC_RULES, "none", "College Handbook",
    ),
    (
        lambda n: "prospectus" in n,
        "prospectus", CAT_ADMISSION, "none", "Prospectus 2026",
    ),
]


def _hierarchy_match(meta: dict | None) -> tuple | None:
    norm = _norm_name(_meta_filename(meta))
    if not norm:
        return None
    for predicate, doc_type, category, hostel_type, display_name in _HIERARCHY:
        if predicate(norm):
            return (doc_type, category, hostel_type, display_name)
    return None


def classify_document(meta: dict | None) -> dict[str, Any]:
    """
    Derive authority metadata for a chunk. Pure; safe to call at ingest or query
    time. Honours authority fields already present on ``meta`` (so a future
    explicit tag wins), otherwise derives them from the filename.

    Returns keys: document_type, category, priority_level, authority_score,
    hostel_type, display_name, version.
    """
    meta = meta or {}
    match = _hierarchy_match(meta)

    if match:
        doc_type, category, hostel_type, display_name = match
        priority_level = TIER1_PRIORITY_LEVEL
        authority_score = TIER1_AUTHORITY_SCORE
    else:
        # Preserve any meaningful existing document_type/category; default to
        # "general" so non-Tier-1 docs are unchanged from today's behaviour.
        doc_type = _clean(meta.get("document_type"), "general")
        category = _clean(meta.get("category"), "general")
        hostel_type = _clean(meta.get("hostel_type"), "none")
        display_name = _clean(meta.get("display_name"), "")
        priority_level = _clean(meta.get("priority_level"), STANDARD_PRIORITY_LEVEL)
        authority_score = _coerce_score(
            meta.get("authority_score"), STANDARD_AUTHORITY_SCORE
        )

    return {
        "document_type": doc_type,
        "category": category,
        "priority_level": priority_level,
        "authority_score": authority_score,
        "hostel_type": hostel_type,
        "display_name": display_name,
        "version": _clean(meta.get("version"), "general"),
    }


def _clean(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return default
    return text


def _coerce_score(value: Any, default: int) -> int:
    try:
        if value in (None, "", "none", "null"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def display_name_for(meta: dict | None) -> str:
    """Human-friendly document name for citations (falls back to filename)."""
    info = classify_document(meta)
    if info["display_name"]:
        return info["display_name"]
    name = _meta_filename(meta)
    if not name:
        return "the available college resources"
    # Strip extension and tidy separators for a readable citation.
    name = re.sub(r"\.(pdf|docx?|txt|md|xlsx?|csv|html?)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"[_]+", " ", name).strip()


def is_tier1(meta: dict | None) -> bool:
    return _hierarchy_match(meta) is not None


# Keyword sets for academic-rules intent (College Handbook territory).
_ACADEMIC_RULES_TERMS = (
    "attendance", "code of conduct", "dress code", "discipline", "disciplinary",
    "examination", "exam rules", "scholarship", "library", "computer lab",
    "student welfare", "committee", "regulation", "regulations", "policy",
    "policies", "vision", "mission", "ragging", "leave rules", "promotion rules",
    "grievance", "id card", "uniform", "facility", "facilities", "amenity",
    "amenities", "campus infrastructure",
)

_HOSTEL_BOYS_TERMS = ("boys hostel", "boys' hostel", "mens hostel", "men's hostel")
_HOSTEL_GIRLS_TERMS = ("girls hostel", "girls' hostel", "womens hostel", "women's hostel", "ladies hostel")

# classify_admission_query categories that map to the Prospectus (admission).
_ADMISSION_CATEGORIES = {
    "admission_process", "admission_dates", "admission_form", "eligibility",
    "personal_eligibility", "documents", "fees", "merit_selection",
    "reservation", "courses",
}


def query_authority_intent(query: str) -> dict[str, Any]:
    """
    Map a user query to the authority categories it relates to. Reuses the
    existing intent classifier (no new query understanding). Returns
    {"categories": set[str], "hostel_type": "boys"|"girls"|"any"|None}.
    """
    # Lazy import to avoid any import cycle (intent imports scoring/text_utils).
    from .intent import (
        classify_admission_query,
        is_attendance_query,
        is_hostel_query,
    )

    q = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    categories: set[str] = set()
    hostel_type: str | None = None

    hostel = False
    try:
        hostel = is_hostel_query(query)
    except Exception:
        hostel = "hostel" in q
    if hostel:
        categories.add(CAT_HOSTEL)
        has_boys = any(t in q for t in _HOSTEL_BOYS_TERMS) or bool(re.search(r"\bboys?\b", q))
        has_girls = any(t in q for t in _HOSTEL_GIRLS_TERMS) or bool(re.search(r"\bgirls?\b", q))
        if has_boys and not has_girls:
            hostel_type = "boys"
        elif has_girls and not has_boys:
            hostel_type = "girls"
        else:
            hostel_type = "any"

    try:
        admission_category = str(classify_admission_query(query).get("category") or "")
    except Exception:
        admission_category = ""
    # A request for syllabus/curriculum/papers is academic content, not a request
    # for the admissions catalogue.  Treating every ``courses`` classification
    # as admission caused the Prospectus to be prepended ahead of a dedicated
    # syllabus even when that syllabus had already been retrieved correctly.
    curriculum_request = bool(re.search(
        r"\b(syllabus|syllabi|curriculum|curricula|papers?|modules?)\b",
        q,
    )) or ("semester" in q and bool(re.search(r"\bsubjects?\b", q)))
    if admission_category in _ADMISSION_CATEGORIES and not curriculum_request:
        categories.add(CAT_ADMISSION)
    if admission_category == "hostel_admission":
        categories.add(CAT_HOSTEL)
        if hostel_type is None:
            hostel_type = "any"

    try:
        attendance = is_attendance_query(query)
    except Exception:
        attendance = "attendance" in q
    if attendance or any(term in q for term in _ACADEMIC_RULES_TERMS):
        categories.add(CAT_ACADEMIC_RULES)

    return {"categories": categories, "hostel_type": hostel_type}


def authority_rank(query: str, meta: dict | None) -> int:
    """
    Integer authority tier used as a sort dimension (higher = preferred):
      2 -> Tier 1 doc whose category matches the query intent (and hostel_type
           matches for hostel queries)
      1 -> Tier 1 doc on a query that IS authority-related but to a different
           Tier 1 topic (still gently preferred over non-Tier-1)
      0 -> non-Tier-1, OR a Tier 1 doc on a query with NO authority intent

    The generic tier (1) is gated on the query having authority intent. Without
    this gate a Prospectus/Handbook chunk received a universal nudge on EVERY
    query (e.g. "head of Chemistry department", "tell me about the NCC"),
    letting a canonical source outrank the genuinely-correct non-Tier-1 document
    on questions that have nothing to do with admissions/rules/hostel.
    """
    match = _hierarchy_match(meta)
    if not match:
        return 0
    doc_type, category, hostel_type, _display = match
    intent = query_authority_intent(query)

    if category in intent["categories"]:
        if category == CAT_HOSTEL:
            want = intent.get("hostel_type")
            # Exact hostel match, or ambiguous/any query -> strong; opposite
            # hostel block on a specific query -> generic only.
            if want in (None, "any") or want == hostel_type:
                return 2
            return 1
        return 2

    # No category match: only grant the generic preference when the query is at
    # least authority-related; on a query with no authority intent, a Tier 1 doc
    # gets no boost at all.
    if intent["categories"]:
        return 1
    return 0


def authority_score_boost(query: str, meta: dict | None) -> float:
    """
    Modest additive score for candidate/lexical stages. Deliberately small
    relative to metadata_boost_score's exact-topic weights (260-500) so it acts
    as a tie-breaker, never an override.
    """
    rank = authority_rank(query, meta)
    if rank >= 2:
        return 120.0
    if rank == 1:
        return 30.0
    return 0.0
