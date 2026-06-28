from __future__ import annotations

import math
import re
import time
from datetime import datetime
from typing import Any


CURRENT_INFO_TERMS = (
    "current",
    "latest",
    "present",
    "today",
    "now",
    "recent",
)


def is_current_information_query(query: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    return any(term in normalized for term in CURRENT_INFO_TERMS)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        year = int(value)
        return year if 1900 <= year <= 2100 else None
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "general", "unknown", "nan"}:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if match:
        return int(match.group(1))
    return None


def _expand_short_year(prefix_year: int, short_year: str) -> int | None:
    if not short_year or len(short_year) != 2:
        return None
    century = prefix_year // 100 * 100
    candidate = century + int(short_year)
    if candidate < prefix_year:
        candidate += 100
    return candidate if 1900 <= candidate <= 2100 else None


def extract_year_from_text(*values: Any) -> int | None:
    years: list[int] = []
    for value in values:
        text = str(value or "")
        if not text:
            continue

        for start, end in re.findall(r"\b(19\d{2}|20\d{2})\s*[-/]\s*(\d{2}|19\d{2}|20\d{2})\b", text):
            start_year = int(start)
            end_year = int(end) if len(end) == 4 else _expand_short_year(start_year, end)
            if end_year:
                years.append(max(start_year, end_year))

        for match in re.findall(r"\b(19\d{2}|20\d{2})\b", text):
            years.append(int(match))

    if not years:
        return None

    plausible = [year for year in years if 1900 <= year <= 2100]
    return max(plausible) if plausible else None


def parse_document_year(meta: dict | None, text: str = "") -> int | None:
    meta = meta or {}
    direct = _coerce_int(meta.get("document_year"))
    if direct:
        return direct
    
    # Try to extract year from parsed date fields first to be robust
    for key in ("document_date", "date", "ModDate", "CreationDate", "last_modified", "Last-Modified"):
        val = meta.get(key)
        if val:
            parsed = parse_document_date_value(val)
            if parsed:
                match = re.match(r"^(\d{4})-\d{2}-\d{2}", parsed)
                if match:
                    return int(match.group(1))

    return extract_year_from_text(
        meta.get("document_date"),
        meta.get("year"),
        meta.get("filename"),
        meta.get("source_filename"),
        meta.get("source_pdf_filename"),
        meta.get("title"),
        meta.get("section_title"),
        meta.get("source_url"),
        text[:4000],
    )


def parse_document_date_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "general", "unknown"}:
        return ""

    # 1. Check PDF metadata date format (e.g. D:20230612143000Z)
    pdf_match = re.match(r"^(?:D:)?(\d{4})(\d{2})(\d{2})", text)
    if pdf_match:
        try:
            return datetime(
                int(pdf_match.group(1)),
                int(pdf_match.group(2)),
                int(pdf_match.group(3)),
            ).date().isoformat()
        except Exception:
            pass

    # 2. Check HTTP Last-Modified format (e.g. Wed, 21 Oct 2015 07:28:00 GMT)
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(text)
        return dt.date().isoformat()
    except Exception:
        pass

    # 3. Check regex patterns for YYYY-MM-DD or DD-MM-YYYY
    patterns = (
        (r"\b(20\d{2}|19\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", ("%Y", "%m", "%d")),
        (r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2}|19\d{2})\b", ("%d", "%m", "%Y")),
    )

    for pattern, order in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        parts = dict(zip(order, match.groups()))
        try:
            return datetime(
                int(parts["%Y"]),
                int(parts["%m"]),
                int(parts["%d"]),
            ).date().isoformat()
        except ValueError:
            try:
                return datetime(
                    int(parts["%Y"]),
                    int(parts["%d"]),
                    int(parts["%m"]),
                ).date().isoformat()
            except Exception:
                pass
        except Exception:
            continue

    return ""


def parse_document_date(meta: dict | None, text: str = "") -> str:
    meta = meta or {}
    for key in ("document_date", "date", "created_at", "updated_at", "ModDate", "CreationDate", "last_modified", "Last-Modified", "crawl_timestamp"):
        parsed = parse_document_date_value(meta.get(key))
        if parsed:
            return parsed
    return parse_document_date_value(text[:1000])


def normalize_source_type(source_type: Any, file_type: Any = "") -> str:
    raw_source = str(source_type or "").strip().lower()
    raw_file = str(file_type or "").strip().lower()
    combined = f"{raw_source} {raw_file}"

    if "links" in combined:
        return "website_links"
    if "image" in combined:
        return "website_image"
    if "pdf" in combined:
        return "pdf"
    if "website" in combined or raw_source in {"site", "web"}:
        return "website"
    if "upload" in combined:
        return "upload"
    if raw_source:
        return raw_source
    return "unknown"


def source_priority(meta: dict | None) -> int:
    meta = meta or {}
    source = normalize_source_type(meta.get("source_type"), meta.get("file_type"))
    # Authority tiers. Official documents (uploaded PDFs/Word/etc. and the
    # official website page) are CO-EQUAL top authority; within that tier the
    # freshness tiebreaker (year/date) decides, so neither silently overrides the
    # other. Crawled navigation/link dumps and images are demoted far below so
    # boilerplate can never outrank an official document.
    #
    # Prior table inverted authority: website_links (90) and website (100) sat
    # ABOVE official pdf (50) and uploaded docs (25), letting web nav text bury
    # official PDFs in close relevance bands.
    if source == "pdf":
        return 100
    if source == "upload":
        return 100
    if source == "website":
        return 100
    if source == "website_image":
        return 35
    if source == "website_links":
        return 20
    return 25


def _timestamp_score(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.timestamp() / 86_400.0
    except Exception:
        return 0.0


def freshness_score(meta: dict | None, text: str = "") -> float:
    meta = meta or {}
    year = parse_document_year(meta, text)
    score = float(year or 0) * 100.0
    date_text = parse_document_date(meta, text)
    if date_text:
        score += _timestamp_score(date_text) / 10.0
    score += _timestamp_score(meta.get("crawl_timestamp")) / 10_000.0
    return score


def _authority_rank(query: str, meta: dict | None) -> int:
    """KNOWLEDGE HIERARCHY tier for a chunk (see rag/authority.py). Lazy import
    keeps this module free of import-order constraints; failures degrade to 0
    (no authority influence) so ranking never breaks."""
    try:
        from .authority import authority_rank
        return authority_rank(query, meta)
    except Exception:
        return 0


def semantic_relevance_score(query: str, doc: str, meta: dict | None, dist: float) -> float:
    from .scoring import (
        admission_evidence_score,
        document_evidence_score,
        fee_evidence_score,
        hostel_evidence_score,
        keyword_score,
        metadata_boost_score,
        person_lookup_relevance_score,
        procedural_relevance_score,
        role_evidence_score,
        staff_relevance_score,
    )

    try:
        distance = float(dist)
    except Exception:
        distance = 999.0
    vector_score = max(0.0, 2.0 - distance) * 20.0
    meta = meta or {}
    return (
        keyword_score(query, doc)
        + vector_score
        + metadata_boost_score(query, doc, meta)
        + admission_evidence_score(query, doc)
        + document_evidence_score(query, doc)
        + role_evidence_score(query, doc)
        + fee_evidence_score(query, doc)
        + hostel_evidence_score(query, doc)
        + procedural_relevance_score(query, doc, meta) * 90.0
        + person_lookup_relevance_score(query, doc, meta) * 140.0
        + staff_relevance_score(query, doc, meta)
    )


def freshness_rank_items(
    query: str,
    items: list[tuple[str, dict, float]],
) -> list[tuple[str, dict, float]]:
    if len(items) <= 1:
        return items

    current_query = is_current_information_query(query)
    semantic_window = 700.0 if current_query else 15.0
    now_year = time.gmtime().tm_year
    scored: list[tuple[tuple[float, float, float, float, int], tuple[str, dict, float]]] = []

    relevance_values = [
        semantic_relevance_score(query, doc, meta or {}, dist)
        for doc, meta, dist in items
    ]
    top_relevance = max(relevance_values) if relevance_values else 0.0

    for idx, ((doc, meta, dist), relevance) in enumerate(zip(items, relevance_values)):
        meta = meta or {}
        year = parse_document_year(meta, doc) or 0
        year_recency = max(0, min(100, year - (now_year - 100))) if year else 0
        fresh = freshness_score(meta, doc) + (year_recency * (75.0 if current_query else 20.0))
        priority = source_priority(meta)
        authority = _authority_rank(query, meta)
        relevance_band = max(0, int((top_relevance - relevance) // semantic_window))

        # Semantic relevance remains primary through the band. Within a close
        # band, the KNOWLEDGE HIERARCHY decides first (a Tier 1 canonical source —
        # Prospectus / Handbook / Hostel Prospectus — outranks notices, circulars
        # and reports), then source priority and freshness. Because authority sits
        # AFTER relevance_band, a lower-priority document still wins when only it
        # contains the answer (different band).
        key = (
            float(relevance_band),
            -float(authority),
            -float(priority),
            -float(fresh),
            -float(relevance),
            idx,
        )
        scored.append((key, (doc, meta, dist)))

    scored.sort(key=lambda item: item[0])
    return [item for _key, item in scored]
