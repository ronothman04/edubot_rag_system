"""Dynamic future-dated-year policy (M-2).

A ``document_year`` in the FUTURE relative to the runtime current year is only a
legitimate freshness signal for a genuinely forward-looking document — a current
academic-session prospectus or admission notice. The other ways a future year
lands in metadata are NOT publication years and must not earn a recency boost:

  * validity / expiry horizons  — "Valid upto 30-05-2027", AICTE "Approval
    Process Handbook 2024-25 to 2027";
  * forward references          — "as we prepare for NAAC 2027", "Ph.D Expected 2027";
  * stray table numbers         — "... 192 2027 637 ..." (a statistical value).

This module is the single source of truth shared by:
  * scripts/audit_future_dated.py    (read-only report)
  * scripts/migrate_future_dated.py  (document-scope correction)
  * rag/freshness.py                 (query-time forward guard for NEW ingests)

Every boundary is derived from the runtime year, so the policy remains valid in
future years without code changes.
"""
from __future__ import annotations

import re
import time
from typing import Any


def current_year() -> int:
    return time.gmtime().tm_year


# A 4-digit year not glued to another DIGIT (so we never pull "2027" out of a
# packed table value like "1922027"), yet tolerant of adjacent letters or
# underscores in a filename such as "overall_2024.pdf" / "doc_2019College.pdf"
# where a plain \b boundary fails.
_LOOSE_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

# 4-digit alternatives come BEFORE ``\d{2}`` so "2026-2027" captures "2027" as the
# end year, not just its first two digits.
_SESSION_RANGE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})\s*[-–/]\s*(19\d{2}|20\d{2}|\d{2})(?!\d)")

_SESSION_CONTEXT = (
    "prospectus", "admission", "session", "academic year", "academic session",
    "fees structure", "fee structure", "intake",
)
_VALIDITY_CONTEXT = (
    "valid from", "valid upto", "valid up to", "valid till", "valid until",
    "validity", "w.e.f", "with effect from", "expiry", "expires",
    "approval process handbook", "extension of approval", "accredit",
)
_FORWARD_REF = (
    "prepare for", "preparing for", "expected", "proposed", "upcoming",
    "will be", "to be held", "by the year", "target",
)

_FORWARD_DOC_TYPES = {"prospectus", "admission", "hostel_prospectus"}


def permissive_identifier_year(*values: Any, not_equal: int | None = None) -> int | None:
    """Best plausible non-future year from identifier fields (filename/title/url),
    tolerant of digits glued to letters/underscores. Ignores ``not_equal`` (the
    future year itself) and anything after the runtime current year."""
    cy = current_year()
    years: list[int] = []
    for value in values:
        for match in _LOOSE_YEAR.findall(str(value or "")):
            year = int(match)
            if year == not_equal:
                continue
            if 1900 <= year <= cy:
                years.append(year)
    return max(years) if years else None


def _windows(text: str, year: str, width: int = 70) -> list[str]:
    lowered = str(text or "")
    out = []
    for match in re.finditer(re.escape(year), lowered):
        out.append(lowered[max(0, match.start() - width): match.end() + width].lower())
    return out


def best_true_year(document_year: int, text: str, meta: dict | None, cy: int | None = None) -> int | None:
    """The document's most defensible non-future year: an identifier/date year if
    present, else the newest in-body year that is not itself in the future."""
    meta = meta or {}
    if cy is None:
        cy = current_year()
    identifier = permissive_identifier_year(
        meta.get("filename"), meta.get("source_filename"),
        meta.get("source_pdf_filename"), meta.get("title"),
        meta.get("pdf_title"), meta.get("source_url"),
        meta.get("document_date"),
        not_equal=document_year,
    )
    if identifier:
        return identifier
    body_years = [int(m) for m in _LOOSE_YEAR.findall(str(text or "")) if int(m) <= cy]
    return max(body_years) if body_years else None


def _is_forward_doc(meta: dict) -> bool:
    doc_type = str(meta.get("document_type", "")).lower()
    if doc_type in _FORWARD_DOC_TYPES:
        return True
    hay = f"{meta.get('filename', '')} {meta.get('title', '')}".lower()
    return "prospectus" in hay or "admission" in hay


def _has_near_current_session(text: str, document_year: int, cy: int) -> bool:
    for a, b in _SESSION_RANGE.findall(str(text or "")):
        start = int(a)
        end = int(b) if len(b) == 4 else (start // 100 * 100 + int(b))
        if end == document_year and start >= cy - 1:
            return True
    return False


def future_year_is_supported(document_year: int, text: str, meta: dict | None,
                             cy: int | None = None) -> bool:
    """Cheap query-time check: may this future year earn a recency boost? True
    only for a forward-looking document (or one the audit already marked
    supported) that carries a current academic-session range."""
    meta = meta or {}
    if cy is None:
        cy = current_year()
    if str(meta.get("document_year_audit", "")).lower() == "supported":
        return True
    if _is_forward_doc(meta) and _has_near_current_session(text, document_year, cy):
        return True
    return False


def classify_future_year(document_year: int, text: str, meta: dict | None,
                         cy: int | None = None) -> dict:
    """Classify a future ``document_year`` and propose an action. Pure + dynamic.

    Returns a dict with: classification, confidence, keep (bool), true_year
    (the demote target, or the future year itself when kept), and a human action.
    """
    meta = meta or {}
    if cy is None:
        cy = current_year()
    year_str = str(document_year)
    windows = _windows(text, year_str)
    true_year = best_true_year(document_year, text, meta, cy)
    near_session = _has_near_current_session(text, document_year, cy)
    has_session_ctx = any(term in str(text or "").lower() for term in _SESSION_CONTEXT)
    forward_doc = _is_forward_doc(meta)

    def near(markers) -> bool:
        return any(any(mk in window for mk in markers) for window in windows)

    # 1) Genuine current academic-session document -> KEEP the future year.
    if near_session and (has_session_ctx or forward_doc):
        return {
            "classification": "SUPPORTED_VALID", "confidence": "high", "keep": True,
            "true_year": document_year,
            "action": "keep future year (current academic-session document)",
        }
    # 2) Validity / accreditation / approval horizon -> DEMOTE (not a pub year).
    if near(_VALIDITY_CONTEXT):
        return {
            "classification": "UNSUPPORTED_AMBIG", "confidence": "high", "keep": False,
            "true_year": true_year,
            "action": "demote: validity/expiry horizon, not a publication year",
        }
    # 3) Forward reference to a future event -> DEMOTE.
    if near(_FORWARD_REF):
        return {
            "classification": "UNSUPPORTED_AMBIG", "confidence": "high", "keep": False,
            "true_year": true_year,
            "action": "demote: forward reference to a future event",
        }
    # 4) Glued between other digits -> a table/statistical number, not a year.
    if any(re.search(r"\d\s*" + re.escape(year_str) + r"\s*\d", window) for window in windows):
        return {
            "classification": "MALFORMED_OCR", "confidence": "medium", "keep": False,
            "true_year": true_year,
            "action": "demote: appears as a table/statistical number, not a year",
        }
    # 5) Inferred-but-credible: forward-looking doc type but no explicit session
    #    range (e.g. a prospectus whose range didn't survive extraction).
    if forward_doc:
        return {
            "classification": "INFERRED_CREDIBLE", "confidence": "medium", "keep": True,
            "true_year": document_year,
            "action": "keep future year (forward-looking document type)",
        }
    # 6) Anything else future -> unsupported.
    return {
        "classification": "UNSUPPORTED_AMBIG", "confidence": "low", "keep": False,
        "true_year": true_year,
        "action": "demote: isolated future number, no forward-looking support",
    }
