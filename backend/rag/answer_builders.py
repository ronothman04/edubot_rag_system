from __future__ import annotations

"""
rag/answer_builders.py
Structured markdown validation and enrichment helpers for St. Anthony's College EduBot.
Includes validation functions for person lookup queries and supporting action detail builders.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from db import collection

from .config import DEBUG_RAG
from .filters import metadata_allows_query, meta_text
from .intent import (
    ROLE_QUERY_ALIASES,
    extract_role_query,
    is_person_lookup_query,
    get_requested_person_title,
)
from .scoring import _person_name_regex
from .text_utils import (
    normalize_text,
    clean_text,
    fix_ocr_casing,
)


def debug_rag(message: str, *values: Any) -> None:
    """Redirect debug statements to the logging module when DEBUG_RAG is active."""
    if DEBUG_RAG:
        logging.info(f"[DEBUG_RAG] {message} " + " ".join(map(str, values)))


def _clean_candidate_name(name: str) -> str:
    name = fix_ocr_casing(clean_text(name))
    name = re.sub(r"\s+", " ", name).strip(" .:-–—|,;")
    return name


def _looks_like_person_name(name: str) -> bool:
    n = normalize_text(name)
    if not n:
        return False
    bad_words = [
        "role", "within", "college", "structure", "provided", "information",
        "section", "source", "page", "file", "committee", "designation",
        "name", "members", "student", "course", "programme", "department",
        "office", "contact", "handbook", "prospectus", "available", "resources",
        "url", "http", "hostel", "vice principal", "principal", "warden",
        "superintendent", "chairman", "coordinator", "secretary",
        "then", "pay", "submit", "application", "permission", "rooms",
        "allotted", "produce", "payment", "confirmation", "mess", "fees",
        "interview", "appointed",
    ]
    if any(bad in n for bad in bad_words):
        return False
    words = name.split()
    if not (2 <= len(words) <= 7):
        return False
    if not re.match(r"^(?:Dr\.?|Br\.?|Sr\.?|Fr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?|[A-Z])", name.strip()):
        return False
    return bool(re.search(r"[A-Za-z]", name))


def context_has_likely_person_name_for_title(query: str, context: str) -> bool:
    if not is_person_lookup_query(query):
        return True

    title = get_requested_person_title(query)
    if not title:
        return False

    c = context or ""
    q_norm = normalize_text(query)
    c_norm = normalize_text(c)
    if "girls hostel" in q_norm or "girl hostel" in q_norm:
        if not any(marker in c_norm for marker in ["girls hostel", "girl s hostel", "mamma margaret", "mama margaret", "margaret hall"]):
            return False
    if "boys hostel" in q_norm or "boy hostel" in q_norm:
        if not any(marker in c_norm for marker in ["boys hostel", "boy s hostel", "stephen hall"]):
            return False

    title_aliases = [title]
    role_case = extract_role_query(query)
    role = role_case.get("role")
    if role:
        title_aliases.extend(alias for alias, mapped in ROLE_QUERY_ALIASES if mapped == role)
    if title == "hod":
        title_aliases.extend(["head of department", "head"])
    if "warden" in title or "hostel" in normalize_text(query) or title in {"superintendent", "matron", "rector", "in charge"}:
        title_aliases.extend([
            "warden",
            "hostel warden",
            "boys hostel warden",
            "girls hostel warden",
            "superintendent",
            "hostel superintendent",
            "matron",
            "rector",
            "in charge",
            "hostel in charge",
        ])
    title_aliases = list(dict.fromkeys(alias for alias in title_aliases if alias))

    name_pattern = _person_name_regex()
    valid_titles = [r"\s+".join(re.escape(part) for part in alias.split()) for alias in title_aliases]
    title_pattern = r"(?:%s)" % "|".join(valid_titles)

    patterns = [
        rf"\b{title_pattern}\b\s*[:\-–—]\s*({name_pattern})",
        rf"({name_pattern})\s*[,|\-–—:]?\s*\b{title_pattern}\b",
        rf"({name_pattern})\s*,\s*(?:designation\s*[:\-])?\s*\b{title_pattern}\b",
        rf"\b{title_pattern}\b.{{0,120}}?({name_pattern})",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, c, flags=re.IGNORECASE | re.DOTALL):
            candidate = _clean_candidate_name(match.group(1) if match.groups() else match.group(0))
            if _looks_like_person_name(candidate):
                return True

    bad_window_phrases = [
        "then pay",
        "pay the",
        "submit",
        "application",
        "permission",
        "rules",
        "mess fees",
        "fee payment",
        "interview",
        "appointed date",
    ]
    lower_c = c.lower()
    for alias in title_aliases:
        alias_lower = alias.lower()
        start_at = 0
        while True:
            idx = lower_c.find(alias_lower, start_at)
            if idx == -1:
                break
            start = max(0, idx - 120)
            end = min(len(c), idx + 160)
            window = c[start:end]
            window_norm = normalize_text(window)
            if any(bad in window_norm for bad in bad_window_phrases):
                start_at = idx + len(alias_lower)
                continue
            for match in re.finditer(name_pattern, window):
                candidate = _clean_candidate_name(match.group(0))
                if _looks_like_person_name(candidate):
                    return True
            start_at = idx + len(alias_lower)

    return False


def invalid_person_lookup_answer(query: str, answer: str) -> bool:
    if not is_person_lookup_query(query):
        return False

    a = (answer or "").lower()
    bad_phrases = [
        "is then",
        "is pay",
        "is submit",
        "is submitted",
        "is application",
        "is permission",
        "is fees",
        "is rules",
        "pay the mess fees",
        "submit the form",
        "application form",
        "permission of the",
    ]

    if any(phrase in a for phrase in bad_phrases):
        return True

    has_capitalized_name = False
    for match in re.finditer(_person_name_regex(), answer or ""):
        if _looks_like_person_name(match.group(0)):
            has_capitalized_name = True
            break

    return not has_capitalized_name


# Person-name shapes used by the principal resolver. A "principal name" is a
# religious/academic honorific followed by 1–4 capitalised words, optionally
# trailed by an order suffix ("SDB") and/or degree (", PhD").
_PRINCIPAL_TITLE = r"(?:Rev\.?\s*)?(?:Dr\.?\s*)?(?:Fr\.?|Br\.?|Sr\.?)"
_PRINCIPAL_NAME = (
    rf"{_PRINCIPAL_TITLE}\s+[A-Z][A-Za-z.'’-]+"
    rf"(?:\s+[A-Z][A-Za-z.'’-]+){{0,3}}"
)
# "<Name> ... took over as the Nth Principal ...": the ordinal makes the
# *current* holder unambiguous (9th supersedes 8th) regardless of how many
# stale documents still list an earlier principal.
_PRINCIPAL_TENURE_RE = re.compile(
    rf"({_PRINCIPAL_NAME})\s+took\s+over\s+as\s+the\s+(\d+)(?:st|nd|rd|th)\s+Principal\b([^.]*)",
    flags=re.IGNORECASE,
)
# "<Name>[ SDB][, PhD] Principal" signature/label form (used for full-name
# resolution and as a context fallback). \s spans newlines so a governance
# block like "Fr. Arcadius Puwein SDB, PhD\nPrincipal of ..." still matches.
_PRINCIPAL_SIG_RE = re.compile(
    rf"\b({_PRINCIPAL_NAME}(?:\s+SDB)?(?:,\s*PhD)?)\s+Principal\b",
    flags=re.IGNORECASE,
)
# Honorifics/suffixes stripped when reducing a name to its identity tokens.
_NAME_STOPWORDS = {"rev", "dr", "fr", "br", "sr", "sdb", "phd", "vice"}


def _name_identity_tokens(name: str) -> set[str]:
    """Lowercased personal-name tokens (honorifics/suffixes removed)."""
    tokens = re.findall(r"[A-Za-z]+", name.lower())
    return {t for t in tokens if t not in _NAME_STOPWORDS and len(t) > 1}


def _iter_corpus_docs() -> list[tuple[str, dict]]:
    """All non-deleted corpus documents (BM25 cache first, ChromaDB fallback)."""
    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        import rag.bm25_index as _bm

        if _bm._bm25_model is None:
            load_bm25_index()
        docs, metas = get_all_documents_and_metas()
        if docs:
            return list(zip(docs, metas))
    except Exception:
        pass
    try:
        res = collection.get(include=["documents", "metadatas"], limit=8000)
        return list(zip(res.get("documents", []), res.get("metadatas", [])))
    except Exception:
        return []


def _fullest_principal_name(identity: set[str], docs: list[tuple[str, dict]]) -> str | None:
    """Best (fullest) signature-form name matching an identity token set."""
    best: str | None = None
    for text, meta in docs:
        if not metadata_allows_query(meta or {}):
            continue
        for match in _PRINCIPAL_SIG_RE.finditer(text or ""):
            candidate = _clean_candidate_name(match.group(1))
            cand_tokens = _name_identity_tokens(candidate)
            if "vice" in candidate.lower() or not cand_tokens & identity:
                continue
            if best is None or (len(candidate.split()), len(candidate)) > (
                len(best.split()),
                len(best),
            ):
                best = candidate
    return best


def _source_from_evidence(meta: dict, text: str) -> dict:
    """Build a UI source dict (build_context shape) from an evidence chunk."""
    meta = meta or {}
    filename = str(meta.get("filename") or meta.get("source") or "Document")
    try:
        from .authority import display_name_for

        display = display_name_for(meta) or filename
    except Exception:
        display = filename
    page = meta.get("page", "?")
    return {
        "id": 1,
        "file": display,
        "page": page,
        "page_label": meta.get("page_label") or page,
        "chunk_index": meta.get("chunk_index", 0),
        "text": str(text or "")[:600],
        "source_url": str(meta.get("source_url", "") or ""),
        "found_on_url": str(meta.get("found_on_url", "") or ""),
        "file_type": str(meta.get("file_type", "") or ""),
        "source_type": str(meta.get("source_type", "") or ""),
        "scope": meta.get("scope", "official"),
        "department": meta.get("department", "general"),
        "year": meta.get("year", "general"),
        "document_type": meta.get("document_type", "general"),
    }


def _resolve_current_principal_detail() -> tuple[str, dict, str] | None:
    """Resolve the current principal plus the tenure evidence that proves it.

    Stale documents (handbooks, annual reports, committee tables) far outnumber
    the notice of a new appointment, so a majority/similarity vote elects the
    previous principal. Instead we anchor on explicit tenure evidence — the
    "took over as the Nth Principal" ordinal — and pick the highest ordinal
    (most recent tenure). Returns (full_name, evidence_meta, evidence_text), or
    None when no tenure evidence exists (caller then falls back to context)."""
    docs = _iter_corpus_docs()
    if not docs:
        return None

    # name string -> (ordinal, latest year seen); + evidence (meta, text) per name.
    tenures: dict[str, tuple[int, int]] = {}
    evidence: dict[str, tuple[dict, str]] = {}
    for text, meta in docs:
        if not metadata_allows_query(meta or {}):
            continue
        for match in _PRINCIPAL_TENURE_RE.finditer(text or ""):
            name = _clean_candidate_name(match.group(1))
            try:
                ordinal = int(match.group(2))
            except (TypeError, ValueError):
                continue
            year_match = re.search(r"(?:19|20)\d{2}", match.group(3) or "")
            year = int(year_match.group(0)) if year_match else 0
            prev = tenures.get(name)
            if prev is None or (ordinal, year) > prev:
                tenures[name] = (ordinal, year)
                evidence[name] = (meta or {}, text or "")

    if not tenures:
        return None

    winner = max(tenures.items(), key=lambda item: item[1])[0]
    identity = _name_identity_tokens(winner)
    if not identity:
        return None

    full_name = _fullest_principal_name(identity, docs) or winner
    ev_meta, ev_text = evidence[winner]
    return full_name, ev_meta, ev_text


def resolve_current_principal() -> str | None:
    """Full name of the current principal, or None (see _resolve_current_principal_detail)."""
    detail = _resolve_current_principal_detail()
    return detail[0] if detail else None


def current_principal_source() -> dict | None:
    """Citation source for the current-principal fact (the tenure evidence doc)."""
    detail = _resolve_current_principal_detail()
    if not detail:
        return None
    _, meta, text = detail
    return _source_from_evidence(meta, text)


def _principal_name_from_context(context: str) -> str | None:
    """Fallback: fullest '<Name> Principal' signature in the provided context,
    excluding vice-principal matches."""
    matches: list[str] = []
    for match in _PRINCIPAL_SIG_RE.finditer(context or ""):
        candidate = _clean_candidate_name(match.group(1))
        if "vice" in candidate.lower():
            continue
        matches.append(candidate)
    if not matches:
        return None
    return max(matches, key=lambda value: (len(value.split()), len(value)))


def build_current_principal_answer(query: str, context: str) -> str | None:
    """Return a stable, citation-free answer for principal role/name lookups.

    Fires for genuine principal questions ("who is the principal", "current
    principal", "name of the principal") but never for *vice* principal. The
    answer is resolved from corpus-wide tenure evidence first, so it stays
    correct even when retrieval surfaces stale committee tables naming a former
    principal."""
    q = normalize_text(query)
    if "principal" not in q or "vice principal" in q or "vice-principal" in q:
        return None

    wants_current = any(term in q for term in ("current", "present", "now"))
    role = extract_role_query(query).get("role")
    is_principal_lookup = role == "principal" and (
        wants_current or "who" in q or is_person_lookup_query(query)
    )
    if not (is_principal_lookup or wants_current):
        return None

    # Corpus-wide tenure evidence is authoritative; fall back to whatever the
    # retrieved context asserts only when no tenure statement exists.
    name = resolve_current_principal() or _principal_name_from_context(context)
    if not name:
        return None

    return f"The present principal of St. Anthony's College is {name}."


def _dedupe_text_items(items: list[str]) -> list[str]:
    seen = set()
    res = []
    for item in items:
        norm = normalize_text(item)
        if norm not in seen:
            seen.add(norm)
            res.append(item)
    return res


def _clean_list_item(item: str) -> str:
    item = fix_ocr_casing(clean_text(item))
    item = re.sub(r"^\s*(?:\d+[\).:-]?|[-*•]+)\s*", "", item)
    item = re.sub(r"\s+", " ", item).strip(" .;:-")
    return item
def _support_detail_context(query: str, where_filter: dict | None = None) -> str:
    try:
        from .bm25_index import get_all_documents_and_metas, load_bm25_index
        from .bm25_index import _bm25_model
        from .retrieval import metadata_matches_where_filter

        if _bm25_model is None:
            load_bm25_index()

        all_docs, all_metas = get_all_documents_and_metas()
        
        if all_docs:
            docs_to_score = all_docs
            metas_to_score = all_metas
        else:
            kwargs: dict[str, Any] = {
                "include": ["documents", "metadatas"],
                "limit": 5000,
            }
            if where_filter:
                kwargs["where"] = where_filter
            result = collection.get(**kwargs)
            docs_to_score = result.get("documents", [])
            metas_to_score = result.get("metadatas", [])
    except Exception:
        return ""

    q_norm = normalize_text(query)
    scored: list[tuple[float, str]] = []
    for doc, meta in zip(docs_to_score, metas_to_score):
        meta = meta or {}
        if not metadata_allows_query(meta):
            continue
        if all_docs and not metadata_matches_where_filter(meta, where_filter):
            continue
        text = str(doc or "")
        norm = normalize_text(text + " " + meta_text(meta))
        score = 0.0

        if "admission.anthonys.ac.in" in text:
            score += 1200.0
        if "college offices" in norm or ("office 3" in norm and "admission and examinations" in norm):
            score += 1000.0
        if "reception" in norm and "all enquiries" in norm:
            score += 700.0
        if "principal@anthonys.ac.in" in text or "anthony@anthonys.ac.in" in text:
            score += 900.0
        if "www.anthonys.ac.in" in text:
            score += 700.0
        if any(term in q_norm for term in ["hostel", "warden", "hall", "accommodation"]):
            if "hostel" in norm or "warden" in norm:
                score += 500.0
        if any(term in q_norm for term in ["admission", "apply", "eligibility", "eligible", "join"]):
            if "admission" in norm or "application" in norm:
                score += 500.0

        if score > 0:
            scored.append((score, text))

    scored.sort(key=lambda item: item[0], reverse=True)
    return "\n---\n".join(text for _score, text in scored[:8])
def _extract_office_lines(text: str) -> list[str]:
    selected: list[str] = []
    normalized = re.sub(r"\s+", " ", fix_ocr_casing(clean_text(text)))

    for label, purpose in re.findall(
        r"\b(Reception|Office\s*\d)\s*:\s*([^:]+?)(?=\s+(?:Office\s*\d|Reception|HosTELs|Hostels)\s*:|\s+HosTELs\b|\s+Hostels\b|$)",
        normalized,
        flags=re.IGNORECASE,
    ):
        label = re.sub(r"\s+", " ", label).strip().title()
        purpose = _clean_list_item(purpose)
        purpose = re.split(r"\b(?:Hostels?|STEPHEN HALL|Mamma Margaret Hall)\b", purpose, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .;:-")
        if label and purpose and len(purpose.split()) <= 8:
            selected.append(f"{label}: {purpose}")

    priority = ["Office 3: Admission and Examinations", "Reception: All Enquiries"]
    ordered = [item for item in priority if normalize_text(item) in {normalize_text(x) for x in selected}]
    ordered.extend(item for item in selected if normalize_text(item) not in {normalize_text(x) for x in ordered})
    return _dedupe_text_items(ordered)[:4]


def build_supporting_action_details(query: str, where_filter: dict | None = None) -> str | None:
    context = _support_detail_context(query, where_filter)
    if not context:
        return None

    q_norm = normalize_text(query)
    text = fix_ocr_casing(clean_text(context))
    bullets: list[str] = []

    urls = sorted(set(
        url.rstrip(".,);]")
        for url in re.findall(r"https?://[^\s,;()]+|www\.[^\s,;()]+", text)
    ))
    admission_urls = [url for url in urls if "admission" in normalize_text(url)]
    college_urls = [url for url in urls if "anthonys.ac.in" in normalize_text(url) and url not in admission_urls]

    if any(term in q_norm for term in ["admission", "apply", "eligibility", "eligible", "join", "form"]):
        for url in admission_urls[:1]:
            bullets.append(f"Admission portal: {url}")
    for url in college_urls[:1]:
        bullets.append(f"College website: {url}")

    phones = sorted(set(
        clean_text(match)
        for match in re.findall(r"\(\d{3,5}\)\s*\d{6,8}|\b\d{3,5}[-\s]\d{6,8}\b", text)
    ))
    if phones:
        bullets.append("Phone: " + ", ".join(phones[:4]))

    emails = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)))
    if emails:
        bullets.append("Email: " + ", ".join(emails[:4]))

    office_lines = _extract_office_lines(text)
    if office_lines:
        if any(term in q_norm for term in ["admission", "apply", "eligibility", "eligible", "join", "form"]):
            office_lines = [
                item for item in office_lines
                if "admission and examinations" in normalize_text(item)
                or "all enquiries" in normalize_text(item)
            ]
        if office_lines:
            bullets.append("Relevant office: " + "; ".join(office_lines[:3]))

    unique = _dedupe_text_items(bullets)
    if not unique:
        return None
    return "Useful details from the available college resources:\n" + "\n".join(
        f"- {item}" for item in unique[:8]
    )


def append_supporting_action_details(
    answer: str,
    query: str,
    where_filter: dict | None = None,
) -> str:
    if not answer or "Useful details from the available college resources" in answer:
        return answer

    answer_norm = normalize_text(answer)
    query_norm = normalize_text(query)
    needs_details = (
        "contact the admission office" in answer_norm
        or "contact the college office" in answer_norm
        or "contact the hostel office" in answer_norm
        or "visit the office" in answer_norm
        or "college website" in answer_norm
        or "official website" in answer_norm
        or ("admission office" in answer_norm and "confirm" in answer_norm)
        or (
            any(term in query_norm for term in ["apply", "admission", "eligibility", "eligible", "join", "form"])
            and any(term in answer_norm for term in ["couldn't find", "not clearly confirm", "not in the available"])
        )
    )
    if not needs_details:
        return answer

    details = build_supporting_action_details(query, where_filter)
    if not details:
        return answer
    return answer.rstrip() + "\n\n" + details
