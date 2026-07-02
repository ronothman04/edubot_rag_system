from __future__ import annotations

"""
rag/scoring.py
Chunk relevance scoring functions for EduBot RAG pipeline.
Imports intent.py, text_utils.py, filters.py only at module level.
"""

import re

from .filters import is_toc_candidate, meta_text
from .intent import (
    KNOWN_DEPARTMENT_NAMES,
    ROLE_QUERY_ALIASES,
    classify_admission_query,
    extract_hostel_target_from_query,
    extract_role_query,
    extract_topic_from_query,
    extract_exact_topic,
    get_requested_person_title,
    is_activity_query,
    is_attendance_query,
    is_certificate_course_query,
    is_contact_query,
    is_course_query,
    is_department_query,
    is_fee_query,
    is_fee_table_query,
    is_application_fee_query,
    is_criteria_query,
    is_head_query,
    is_hostel_query,
    is_procedural_query,
    is_person_lookup_query,
    is_postgraduate_course_query,
    is_website_links_query,
    detect_query_intents,
    get_primary_intent,
    extract_entities,
    is_warden_query,
    is_staff_query,
    is_club_query,
    is_cell_or_committee_query,
)
from .text_utils import (
    filename_title_hint,
    important_words,
    normalize_query,
    normalize_text,
)

HOSTEL_POSITIVE_TERMS = [
    "hostel", "application", "admission", "admission form", "application form",
    "warden", "parent", "guardian", "submit", "submitted", "prospectus",
    "boys hostel", "girls hostel", "hostel admission", "hostel rules", "hostel fees",
    "eligibility",
]

HOSTEL_NEGATIVE_TERMS = [
    "societies registration act", "registered under the societies",
    "society which is registered", "memorandum of association", "constitution of the society",
]

PROCEDURAL_QUERY_MARKERS = [
    "how to apply", "how to submit", "how to register", "how to get admission",
    "procedure", "application process", "admission process",
]

PROCEDURAL_POSITIVE_TERMS = [
    "application", "form", "submit", "submitted", "office", "warden",
    "principal", "admission", "parent", "guardian", "documents required", "eligibility",
]

PROCEDURAL_NEGATIVE_TERMS = [
    "general background", "history", "legal registration", "committee",
    "committee members", "societies registration act", "registered under the societies",
    "society which is registered", "memorandum of association", "constitution of the society",
]


def _role_regex(role: str) -> str:
    """Generate regex for matching role names with aliases."""
    aliases = [alias for alias, mapped in ROLE_QUERY_ALIASES if mapped == role]
    aliases.append(role)
    if role == "hod":
        aliases.extend(["head of department", "head"])
    unique = list(dict.fromkeys(
        re.sub(r"\s+", " ", str(alias or "").lower()).strip()
        for alias in aliases
        if alias
    ))
    return r"(?:%s)" % "|".join(
        r"\s+".join(re.escape(part) for part in alias.split())
        for alias in sorted(unique, key=len, reverse=True)
    )


def _person_name_regex() -> str:
    """Regex matching person names with optional titles."""
    name_word = r"(?:[A-Z][A-Za-z.'-]+|[A-Z]\.?)"
    return (
        r"(?:Dr\.?|Prof\.?|Professor|Mr\.?|Mrs\.?|Ms\.?|Miss|Fr\.?|Rev\.?|Sr\.?|Shri|Smt\.?)?\s*"
        rf"{name_word}(?:\s+{name_word}){{1,5}}"
    )


# TODO: split
def metadata_boost_score(query: str, document: str, meta: dict | None) -> float:
    """Calculate metadata-based scoring boost for retrieved chunks."""
    meta = meta or {}
    q_norm = normalize_query(query)
    d_norm = normalize_text(document)
    section_norm = normalize_text(str(meta.get("section_title", "") or ""))
    meta_norm = normalize_text(meta_text(meta))
    first_300_norm = normalize_text((document or "")[:300])
    source_url_norm = normalize_text(str(meta.get("source_url", "") or ""))
    q_words = important_words(query)
    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)
    score = 0.0

    if q_norm and q_norm in d_norm:
        score += 260.0
    if q_norm and q_norm in first_300_norm:
        score += 220.0
    if q_norm and q_norm in section_norm:
        score += 320.0
    if exact_topic:
        topic_norm = normalize_text(exact_topic)
        if topic_norm in section_norm:
            score += 500.0
        if topic_norm in first_300_norm:
            score += 280.0
        if topic_norm in meta_norm:
            score += 180.0
        if topic_norm and source_url_norm and topic_norm in source_url_norm:
            score += 350.0

    for word in q_words:
        if word in section_norm:
            score += 55.0
        if word in first_300_norm:
            score += 35.0
        if word in meta_norm:
            score += 25.0
        if source_url_norm and word in source_url_norm:
            score += 20.0

    # Title/heading coverage: reward chunks whose SECTION TITLE covers the salient
    # query words. The heading (e.g. "Profile of the College") is the strongest
    # disambiguator but is otherwise weak in body-only scoring — this makes a
    # near-complete title match decisive over a partial one ("Computer Dept Profile").
    if q_words and section_norm:
        title_hits = [w for w in q_words if w in section_norm]
        if title_hits:
            coverage = len(title_hits) / len(q_words)
            score += 120.0 * coverage
            if coverage >= 0.6:
                score += 220.0

    # Filename-stem match: query terms appearing in the document name (e.g. a
    # query for "about" / "profile" preferring doc_About.pdf).
    filename_norm = normalize_text(filename_title_hint(str(meta.get("filename", "") or "")))
    if q_words and filename_norm:
        fname_hits = [w for w in q_words if len(w) > 3 and w in filename_norm]
        score += len(fname_hits) * 60.0

    if is_website_links_query(query) and meta.get("source_type") == "website_links":
        score += 3500.0

    important_terms = [
        "admission", "application", "eligibility", "fee", "fees", "department",
        "course", "programme", "hostel", "attendance", "examination", "contact",
        "faculty", "staff", "principal", "head", "documents", "scholarship",
        "library", "committee", "club", "cell",
    ]
    for term in important_terms:
        if term in q_norm and term in d_norm:
            score += 45.0

    score += hostel_relevance_score(query, document, meta) * 90.0
    score += procedural_relevance_score(query, document, meta) * 70.0
    score += person_lookup_relevance_score(query, document, meta) * 120.0
    score += staff_relevance_score(query, document, meta)

    if is_postgraduate_course_query(query):
        if "post graduate courses" in section_norm or "postgraduate courses" in section_norm:
            score += 1200.0
        if "at present the college offers four pg courses" in d_norm:
            score += 1000.0
        if "msc biotechnology" in d_norm and "mca" in d_norm and "pgdca" in d_norm:
            score += 700.0
        if "undergraduate" in section_norm and "post graduate" not in section_norm:
            score -= 600.0

    if is_warden_query(query):
        target = extract_hostel_target_from_query(query)
        target_norm = normalize_text(target or "")
        has_warden_context = any(
            marker in d_norm
            for marker in ["warden", "hostel warden", "hall warden", "superintendent"]
        )
        if target_norm and target_norm in d_norm and has_warden_context:
            score += 4500.0
        elif has_warden_context:
            score += 450.0
        else:
            score -= 900.0

    if is_toc_candidate(document, meta) and "contents" not in q_norm:
        score -= 1600.0

    # KNOWLEDGE HIERARCHY tie-breaker: prefer Tier 1 canonical sources when the
    # query relates to their topics. Weight is modest relative to the exact-topic
    # boosts above (260-500), so it breaks ties without overriding a genuine
    # match. Propagates through every reorder path that calls this function.
    try:
        from .authority import authority_score_boost
        score += authority_score_boost(query, meta)
    except Exception:
        pass

    return score


def contact_marker_score(document: str) -> float:
    """Assess if a document contains contact markers (phone, email, etc.)."""
    d_norm = normalize_text(document)
    padded = f" {d_norm} "
    score = 0.0
    weighted_markers = {
        "@": 500.0, "email": 350.0, "e mail": 350.0, "fax": 300.0,
        "telephone": 280.0, "phone": 280.0, "mobile": 280.0,
        "website": 240.0, "www": 240.0, ".com": 220.0, ".in": 220.0,
        "address": 180.0,
    }
    for marker, weight in weighted_markers.items():
        if marker in d_norm:
            score += weight
    if " ph " in padded:
        score += 260.0
    return score


def is_table_of_contents_chunk(document: str) -> bool:
    """Assess if a chunk looks like a table of contents page."""
    d_norm = normalize_text(document)
    raw = (document or "").lower()
    if "table of contents" in raw or "contents page no" in raw:
        return True
    if "table of contents" in d_norm or "contents page no" in d_norm:
        return True
    dotted_lines = len(re.findall(r"\.{8,}", document or ""))
    if dotted_lines >= 3:
        return True
    if " page no " in f" {d_norm} " and dotted_lines >= 1:
        return True
    return False


def has_head_marker(document: str) -> bool:
    """Check if the document references committee coordinator or warden titles."""
    d_norm = normalize_text(document)
    return bool(re.search(
        r"\b(head|director|incharge|hod|principal|chairman|chairperson|secretary|coordinator|warden|superintendent)\b"
        r"|\bin\s+charge\b|\bvice\s+principal\b|\bhostel\s+warden\b|\bhall\s+warden\b",
        d_norm,
    ))


def has_head_marker_near_topic(document: str, topic: str | None) -> bool:
    """Check if a head title appears close to a topic keyword."""
    if not has_head_marker(document):
        return False
    if not topic:
        return True
    d_norm = normalize_text(document)
    topic_norm = normalize_text(topic)
    topic_pos = d_norm.find(topic_norm)
    if topic_pos == -1:
        return False
    marker_positions = [
        m.start()
        for m in re.finditer(
            r"\b(head|director|incharge|hod|principal|chairman|chairperson|secretary|coordinator|warden|superintendent)\b"
            r"|\bin\s+charge\b|\bvice\s+principal\b|\bhostel\s+warden\b|\bhall\s+warden\b",
            d_norm,
        )
    ]
    return any(abs(pos - topic_pos) <= 1200 for pos in marker_positions)


def department_relevance_score(document: str) -> float:
    """Calculate scoring adjustments for general department queries."""
    d_norm = normalize_text(document)
    dept_of_count   = len(re.findall(r"\bdepartment of\b", d_norm))
    known_name_count= sum(1 for name in KNOWN_DEPARTMENT_NAMES if name in d_norm)
    score = 0.0
    if "section departments" in d_norm:
        score += 1000.0
    elif " departments " in f" {d_norm} ":
        score += 300.0
    if "/pages/departments/departments.php" in d_norm:
        score += 900.0
    if dept_of_count:
        score += 140.0 + (dept_of_count * 80.0)
    if known_name_count:
        score += min(known_name_count, 8) * 35.0
    if "/pages/departments/dept_" in d_norm and known_name_count <= 2:
        score -= 120.0
    if "events_chronology" in d_norm:
        score -= 1800.0
    if "/pages/facilities/" in d_norm or "/pages/clubs/" in d_norm:
        score -= 300.0
    return max(score, 0.0)


def attendance_relevance_score(document: str) -> float:
    """Calculate scoring adjustments for attendance queries."""
    d_norm = normalize_text(document)
    if "attendance" not in d_norm:
        return 0.0
    score = 100.0
    strong_markers = [
        "75%", "75 percent", "minimum of 75", "minimum 75",
        "required to appear", "appear for the university", "end semester examinations",
        "attendance is required", "attendance requirement", "attendance requirements",
    ]
    raw_lower = (document or "").lower()
    for marker in strong_markers:
        if marker in raw_lower or marker in d_norm:
            score += 220.0
    for marker in ["classes", "lectures", "academic schedule", "leave requirements", "shortage"]:
        if marker in d_norm:
            score += 60.0
    if "signed their attendance" in d_norm and score < 350.0:
        score -= 120.0
    return max(score, 0.0)


def fee_relevance_score(document: str) -> float:
    """Score matching terms for fees structures."""
    text = document or ""
    d_norm = normalize_text(text)
    if "fee" not in d_norm and "fees" not in d_norm and "₹" not in text:
        return 0.0
    score = 0.0
    if "₹" in text or "rs." in d_norm or "rupees" in d_norm:
        score += 180.0
    fee_markers = [
        "fees structure", "fee structure", "common fees", "software licencing fees",
        "software licensing fees", "professional course fee", "laboratory charges",
        "refundable fees", "one time fees", "fees and payments",
        "admission fee", "application fee",
    ]
    for marker in fee_markers:
        if marker in d_norm:
            score += 260.0
    if "per semester" in d_norm:
        score += 160.0
    rupee_count = text.count("₹")
    if rupee_count:
        score += min(rupee_count, 20) * 25.0
    return score


def current_role_evidence_score(query: str, document: str) -> float:
    """Prefer explicit latest-tenure evidence for current role-holder queries."""
    q = normalize_text(query)
    if not any(marker in q for marker in ("current", "present", "now")):
        return 0.0

    d = normalize_text(document)
    role_case = extract_role_query(query)
    role = normalize_text(str(role_case.get("role") or ""))
    if not role and "principal" in q:
        role = "principal"
    if not role or role not in d:
        return 0.0

    score = 0.0
    if re.search(
        rf"\b(?:current|present) {re.escape(role)}\b|"
        rf"\b{re.escape(role)}\b\s*(?:\(|from )\s*\d{{4}}\s*(?:-|to)\s*present",
        d,
    ):
        score += 4000.0
    if re.search(rf"\btook over as (?:the )?\d+(?:st|nd|rd|th) {re.escape(role)}\b", d):
        score += 4000.0
    if re.search(rf"\bappointed as (?:the )?{re.escape(role)}\b|\bassumed (?:office|charge) as (?:the )?{re.escape(role)}\b", d):
        score += 3500.0
    return score


def role_evidence_score(query: str, document: str) -> float:
    """Assess if the document holds details of requested role holders."""
    q = normalize_text(query)
    d = normalize_text(document)
    raw = str(document or "")[:12000]
    if not d:
        return 0.0

    role_case = extract_role_query(query)
    role = role_case.get("role")
    role_terms = [role] if role else []
    if role == "hod":
        role_terms.extend(["head of department", "head"])
    if not role_terms and is_head_query(query):
        role_terms = [
            "principal", "vice principal", "head", "hod", "chairman", "chairperson",
            "coordinator", "secretary", "warden", "superintendent", "director",
        ]
    if not role_terms:
        return 0.0

    score = 0.0
    if any(term and term in d for term in role_terms):
        score += 500.0
    if any(term in d for term in ["name designation", "no name designation", "designation", "office bearers", "authorities", "members"]):
        score += 300.0
    if "no" in d and "name" in d and "designation" in d:
        score += 180.0
    if re.search(r"\|\s*\d+\s*\|[^|]{3,80}\|[^|]*(?:principal|chairman|coordinator|secretary|warden|head|director)", raw, flags=re.IGNORECASE):
        score += 450.0
    if re.search(r"\b\d+\s+[A-Z][A-Za-z.' -]+(?:\s+[A-Z][A-Za-z.' -]+){1,5}\s+(?:Principal|Vice Principal|Chairman|Coordinator|Secretary|Warden|Superintendent|Director|Head)\b", raw):
        score += 450.0
    role_regex = _role_regex(role) if role else r"(?:principal|vice\s+principal|hod|head|chairman|chairperson|coordinator|secretary|warden|superintendent|director)"
    person_name = r"(?:Dr\.?|Br\.?|Sr\.?|Fr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?)?[ \t]*[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+){1,6}"
    if re.search(rf"{person_name}.{{0,90}}{role_regex}|{role_regex}.{{0,90}}{person_name}", raw, flags=re.IGNORECASE | re.DOTALL):
        score += 380.0
    target = role_case.get("target") or extract_topic_from_query(query)
    if target and normalize_text(str(target)) in d:
        score += 2200.0
    elif target:
        score -= 700.0
    if "principal" in q and "principal chairman" in d:
        score += 250.0
    score += current_role_evidence_score(query, raw)
    return score


def admission_evidence_score(query: str, document: str) -> float:
    """Determine query alignment with admission notices."""
    info = classify_admission_query(query)
    category = str(info.get("category") or "")
    if category not in {
        "admission_process", "admission_dates", "admission_form", "eligibility",
        "personal_eligibility", "courses", "documents", "fees", "merit_selection",
        "reservation", "hostel_admission", "contact",
    } and "admission" not in normalize_text(query):
        return 0.0

    d = normalize_text(document)
    score = 0.0
    weighted = {
        "admission": 160.0,
        "application": 130.0,
        "prospectus": 120.0,
        "eligibility": 170.0,
        "eligible": 130.0,
        "merit": 160.0,
        "merit list": 260.0,
        "selection": 150.0,
        "entrance test": 220.0,
        "form": 120.0,
        "documents": 140.0,
        "fee": 100.0,
        "fees": 100.0,
        "counselling": 150.0,
        "last date": 240.0,
        "notification": 180.0,
        "notice": 160.0,
        "application form": 220.0,
        "eligibility criteria": 260.0,
        "qualifying examination": 220.0,
        "minimum marks": 220.0,
    }
    for term, weight in weighted.items():
        if term in d:
            score += weight
    target_course = info.get("target_course")
    if target_course and normalize_text(str(target_course)) in d:
        score += 450.0
    subject = info.get("subject")
    if subject and normalize_text(str(subject)) in d:
        score += 250.0
    return score


def document_evidence_score(query: str, document: str) -> float:
    """Assess alignment with documents required checklist chunks."""
    q = normalize_text(query)
    if not any(term in q for term in ["document", "documents", "certificate", "certificates", "marksheet", "migration", "transfer", "character", "original"]):
        return 0.0
    d = normalize_text(document)
    score = 0.0
    for term in [
        "documents required", "required documents", "certificates", "transfer certificate",
        "migration certificate", "character certificate", "marksheet", "mark sheet",
        "admit card", "photocopy", "original documents", "original certificate",
        "caste certificate", "income certificate", "domicile certificate",
        "documents to be submitted", "documents for admission",
    ]:
        if term in d:
            score += 240.0
    if "admission" in d:
        score += 120.0
    return score


def fee_evidence_score(query: str, document: str) -> float:
    """Assesses alignment with fee breakdowns."""
    if not is_fee_query(query):
        return 0.0
    score = fee_relevance_score(document)
    d = normalize_text(document)
    for term in [
        "admission fee", "application fee", "semester fee", "fee structure",
        "fees structure", "refundable", "refund", "installment", "instalment",
        "online payment", "offline payment", "payment", "charges",
    ]:
        if term in d:
            score += 180.0
    if re.search(r"(?:rs\.?|₹)\s*[\d,]+", document, flags=re.IGNORECASE):
        score += 300.0
    return score


def hostel_relevance_score(query: str, text: str, metadata: dict | None = None) -> float:
    """Score the relevance of hostel terms."""
    q = (query or "").lower()
    t = (text or "").lower()
    meta = metadata or {}

    if "hostel" not in q:
        return 0.0

    score = 0.0

    for term in HOSTEL_POSITIVE_TERMS:
        if term in t:
            score += 1.5

    for term in HOSTEL_NEGATIVE_TERMS:
        if term in t:
            score -= 5.0

    filename = str(meta.get("filename", "")).lower()
    section = str(meta.get("section_title", "")).lower()
    source_pdf = str(meta.get("source_pdf_filename", "")).lower()
    file_text = f"{filename} {source_pdf}"

    if "hostel" in file_text:
        score += 3.0

    if "prospectus" in file_text:
        score += 2.0

    if "hostel" in section:
        score += 2.0

    if "application" in section or "admission" in section:
        score += 2.0

    return score


def procedural_relevance_score(query: str, text: str, metadata: dict | None = None) -> float:
    """Score the relevance of procedural markers."""
    if not is_procedural_query(query):
        return 0.0

    t = normalize_text(text)
    meta = metadata or {}
    score = 0.0

    for term in PROCEDURAL_POSITIVE_TERMS:
        if term in t:
            score += 1.2

    for term in PROCEDURAL_NEGATIVE_TERMS:
        if term in t:
            score -= 4.0

    section = normalize_text(str(meta.get("section_title", "") or ""))
    filename = normalize_text(str(meta.get("filename", "") or ""))
    source_pdf = normalize_text(str(meta.get("source_pdf_filename", "") or ""))
    meta_text_norm = f"{section} {filename} {source_pdf}"

    if any(term in section for term in ["application", "admission", "procedure", "process", "hostel"]):
        score += 2.0
    if "prospectus" in meta_text_norm:
        score += 1.5
    if is_hostel_query(query) and "hostel" in meta_text_norm:
        score += 2.0

    return score


def is_context_relevant_for_hostel(query: str, context: str) -> bool:
    """Check if hostel queries have a high concentration of hostel keywords in context."""
    q = (query or "").lower()
    c = (context or "").lower()

    if "hostel" not in q:
        return True

    important_terms = [
        "hostel", "application", "admission", "form", "warden",
        "parent", "guardian", "submit", "submitted", "prospectus",
    ]
    matches = sum(1 for term in important_terms if term in c)
    return matches >= 3


def hostel_evidence_score(query: str, document: str) -> float:
    """Assesses alignment with hostel guides."""
    q = normalize_text(query)
    if not any(term in q for term in ["hostel", "accommodation", "hosteller", "warden", "hall", "superintendent"]):
        return 0.0
    d = normalize_text(document)
    score = 0.0
    for term in [
        "hostel", "accommodation", "hosteller", "warden", "hall", "superintendent",
        "room", "mess", "hostel admission", "hostel rules", "hostel fee",
        "hostel superintendent", "hall warden", "application form", "parent",
        "guardian", "submit", "submitted", "boys hostel", "girls hostel",
    ]:
        if term in d:
            score += 170.0
    score += hostel_relevance_score(query, document) * 120.0
    score += procedural_relevance_score(query, document) * 80.0
    return score


def club_relevance_score(query: str, document: str) -> float:
    """Assess alignment with extra-curricular club registration notices."""
    q = normalize_text(query)
    t = normalize_text(document)
    if not any(w in q for w in ["club", "clubs", "cell", "cells", "association", "associations", "society", "societies"]):
        return 0.0
    score = 0.0
    club_terms = [
        "club", "clubs", "cell", "cells", "committee", "committees",
        "association", "associations", "society", "societies",
        "student activities", "co curricular", "co-curricular", "extracurricular",
    ]
    for term in club_terms:
        if term in t:
            score += 80.0
    if "/pages/clubs/" in t:
        score += 350.0
    return score


def activity_relevance_score(query: str, document: str) -> float:
    """Score matches for NCC/NSS/Sports/Cultural events."""
    if not is_activity_query(query):
        return 0.0

    t = normalize_text(document)
    score = 0.0

    activity_terms = [
        "co curricular", "co-curricular", "extension activities", "student activities",
        "activities", "ncc", "nss", "rovers", "rangers", "sac seva", "sac-seva",
        "social outreach", "seminar", "seminars", "workshop", "workshops",
        "guest lecture", "guest lectures", "sports", "cultural", "club", "clubs",
    ]
    for term in activity_terms:
        if term in t:
            score += 160.0

    certificate_only_terms = [
        "certificate courses", "career oriented courses", "ugc approved",
        "doeacc", "dca", "ccna", "sap",
    ]
    if any(term in t for term in certificate_only_terms) and score < 300.0:
        score -= 500.0

    rule_noise_terms = [
        "reference books", "library rules", "computer lab",
        "virus creation", "system policies", "equipment should not be tampered",
    ]
    if any(term in t for term in rule_noise_terms) and score < 300.0:
        score -= 400.0

    return max(score, 0.0)


def course_relevance_score(query: str, document: str) -> float:
    """Score alignment with course lists and programme guides."""
    if not is_course_query(query):
        return 0.0
    q_norm = normalize_text(query)
    d_norm = normalize_text(document)

    score = 0.0
    q_acro = q_norm.replace(".", "")
    d_acro = d_norm.replace(".", "")
    q_padded = f" {q_acro} "
    d_padded = f" {d_acro} "

    course_markers = [
        "course", "courses", "programme", "programmes", "undergraduate", "postgraduate",
        "degree", "ba", "bsc", "bcom", "bba", "bca", "ma", "msc", "mcom", "msw", "mca",
        "diploma", "certificate courses",
    ]
    if any(f" {m} " in d_padded for m in course_markers):
        score += 220.0

    pg_terms = ["pg", "postgraduate", "post graduate", "master", "ma", "msc", "mcom", "msw", "mca"]
    ug_terms = ["ug", "undergraduate", "under graduate", "bachelor", "ba", "bsc", "bcom", "bba", "bca"]

    is_pg_query = any(f" {w} " in q_padded for w in pg_terms)
    is_ug_query = any(f" {w} " in q_padded for w in ug_terms)

    if is_pg_query:
        if any(f" {m} " in d_padded for m in pg_terms):
            score += 600.0
        if any(f" {m} " in d_padded for m in ug_terms) and not any(f" {m} " in d_padded for m in pg_terms):
            score -= 400.0

    if is_ug_query:
        if any(f" {m} " in d_padded for m in ug_terms):
            score += 600.0
        if any(f" {m} " in d_padded for m in pg_terms) and not any(f" {m} " in d_padded for m in ug_terms):
            score -= 400.0

    if is_certificate_course_query(query) and "certificate" in d_norm:
        score += 800.0

    exact_topic = extract_exact_topic(query)
    if exact_topic:
        topic_norm = normalize_text(exact_topic)
        topic_variants = {topic_norm}
        if "computer science" in topic_norm:
            topic_variants.update(["computer application", "computer applications", "mca", "pgdca", "computer sciences", "computer"])

        if any(variant in d_norm for variant in topic_variants):
            structure_markers = [
                "major subjects", "minor subjects", "honours", "programme name",
                "intake", "undergraduate programmes", "post graduate courses",
                "master of", "diploma in", "course code", "sl. no.", "sl no",
                "disciplines for fyu", "fyu programmes"
            ]
            if any(marker in d_norm for marker in structure_markers):
                score += 1500.0

    return score


def _criteria_heading_for_query(query: str) -> str | None:
    """Determine criteria heading candidates."""
    q = normalize_text(query)
    if "major" in q:
        return "criteria for choosing a major subject"
    if "minor" in q:
        return "criteria for choosing a minor subject"
    if "mdc" in q or "multi disciplinary" in q or "multidisciplinary" in q:
        return "criteria for choosing mdc"
    if "vac" in q or "value added" in q:
        return "criteria for choosing vac"
    if "sec" in q or "skill enhancement" in q:
        return "criteria for choosing sec"
    if "aec" in q or "ability enhancement" in q:
        return "criteria for choosing aec"
    return None


def criteria_relevance_score(query: str, document: str) -> float:
    """Score alignment with FYUGP subject selection criteria notices."""
    if not is_criteria_query(query):
        return 0.0
    d_norm = normalize_text(document)
    heading = _criteria_heading_for_query(query)
    score = 0.0
    if heading and heading in d_norm:
        score += 2500.0
    elif "criteria for choosing" in d_norm:
        score += 500.0
    elif "criteria" in d_norm and "choosing" in d_norm:
        score += 250.0
    else:
        score -= 350.0
    q_norm = normalize_text(query)
    if "major" in q_norm and "major subject" in d_norm:
        score += 350.0
    if "minor" in q_norm and "minor subject" in d_norm:
        score += 350.0
    return score


# TODO: split
def person_lookup_relevance_score(query: str, text: str, metadata: dict | None = None) -> float:
    """Calculate boost score for finding name lookups (e.g. 'Who is the warden of Stephen Hall?')."""
    q = (query or "").lower()
    t = (text or "").lower()
    meta = metadata or {}

    if not is_person_lookup_query(query):
        return 0.0

    requested_title = get_requested_person_title(query)
    score = 0.0

    if requested_title and requested_title in t:
        score += 5.0

    positive_terms = [
        "name", "designation", "contact", "email", "phone", "staff", "faculty",
        "profile", "department", "committee", "members", "office", "principal",
        "vice principal", "warden", "hod", "head of department", "coordinator",
        "convenor", "secretary", "librarian", "chairperson",
    ]

    negative_terms = [
        "pay the", "pay fees", "mess fees", "submit to", "submitted to",
        "application form", "permission of", "rules", "discipline", "fine",
        "late fee", "registered under", "societies registration act",
        "memorandum of association", "constitution of the society",
    ]

    for term in positive_terms:
        if term in t:
            score += 1.0

    for term in negative_terms:
        if term in t:
            score -= 4.0

    filename = str(meta.get("filename", "")).lower()
    section = str(meta.get("section_title", "")).lower()
    source_pdf = str(meta.get("source_pdf_filename", "")).lower()
    file_text = f"{filename} {source_pdf}"

    if any(x in file_text for x in ["staff", "faculty", "handbook", "prospectus", "committee", "hostel", "department"]):
        score += 1.5

    if requested_title and requested_title in section:
        score += 4.0

    if any(x in section for x in ["staff", "faculty", "committee", "department", "administration", "contact"]):
        score += 2.0

    return score


def chunk_has_staff_evidence(text: str) -> bool:
    """Helper to check if a chunk has staff/faculty member lists."""
    from .intent import chunk_has_staff_evidence as core_helper
    return core_helper(text)


def chunk_looks_like_course_only(text: str) -> bool:
    """Helper to check if a chunk looks like course structure without name lists."""
    from .intent import chunk_looks_like_course_only as core_helper
    return core_helper(text)


def _dept_aliases(dept: str) -> list[str]:
    """Helper to fetch department surface form aliases."""
    from .intent import _dept_aliases as core_helper
    return core_helper(dept)


def staff_relevance_score(query: str, document: str, meta: dict | None = None) -> float:
    """Helper to calculate department staff matching scores."""
    from .intent import staff_relevance_score as core_helper
    return core_helper(query, document, meta)


def score_chunk_by_intent(query: str, document: str, meta: dict | None = None) -> float:
    """Calculate intent-specific alignment scores."""
    score = 0.0
    meta = meta or {}
    
    # 1. Hostel Intent
    if is_hostel_query(query) or is_warden_query(query):
        score += hostel_evidence_score(query, document)
        
    # 2. Staff/Role Intent
    if is_staff_query(query) or is_head_query(query) or is_person_lookup_query(query):
        score += staff_relevance_score(query, document, meta)
        score += role_evidence_score(query, document)
        score += person_lookup_relevance_score(query, document, meta) * 50.0
        
    # 3. Contact Intent
    if is_contact_query(query):
        score += contact_marker_score(document)
        
    # 4. Fee Intent
    if is_fee_query(query) or is_application_fee_query(query) or is_fee_table_query(query):
        score += fee_evidence_score(query, document)
        
    # 5. Course/Program Intent
    if is_course_query(query) or is_certificate_course_query(query) or is_postgraduate_course_query(query):
        score += course_relevance_score(query, document)
        
    # 6. Attendance Intent
    if is_attendance_query(query):
        score += attendance_relevance_score(document)
        
    # 7. Criteria/FYUGP Intent
    if is_criteria_query(query):
        score += criteria_relevance_score(query, document)
        
    # 8. Activity/Club Intent
    if is_activity_query(query):
        score += activity_relevance_score(query, document)
    if is_club_query(query) or is_cell_or_committee_query(query):
        score += club_relevance_score(query, document)
        
    return score


def score_chunk_by_intent_and_entity(query: str, document: str, meta: dict | None = None) -> float:
    return score_chunk_by_intent(query, document, meta)


# TODO: split
def keyword_score(query: str, document: str) -> float:
    """Composite lexical relevance score. Called once per (query, doc) pair."""
    q_norm = normalize_text(query)
    d_norm = normalize_text(document)
    if not q_norm or not d_norm:
        return 0.0

    all_q_words = important_words(query)
    q_words = all_q_words[:15]
    if not q_words:
        return 0.0

    score = 0.0
    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)

    if exact_topic and exact_topic in d_norm:
        score += 150.0
    if q_norm in d_norm:
        score += 70.0

    matched = [w for w in q_words if w in d_norm]
    score += len(matched) * 10.0
    if matched and len(matched) == len(q_words):
        score += 35.0

    if len(q_words) >= 2:
        positions = [d_norm.find(w) for w in q_words if d_norm.find(w) != -1]
        if positions and max(positions) - min(positions) < 700:
            score += 25.0

    useful_markers = [
        "department of", "departments", "academic departments", "head", "head ug", "director pg",
        "teaching staff", "faculty", "no name designation", "principal chairman", "vice principal",
        "coordinator", "assistant coordinator", "member", "rules", "guidelines", "attendance",
        "minimum attendance", "75 percent", "75%", "fee", "admission", "eligibility", "programme",
        "programmes", "course", "courses", "undergraduate", "postgraduate", "degree",
        "hostel", "library", "club", "clubs", "association", "society",
    ]
    for marker in useful_markers:
        if marker in d_norm:
            score += 4.0

    if is_contact_query(query):
        cs = contact_marker_score(document)
        score += cs if cs > 0 else -80.0

    if is_head_query(query):
        score += role_evidence_score(query, document)
        score += 120.0 if has_head_marker_near_topic(document, exact_topic) else -80.0

    # Skip the department-content penalty for head/person lookups so a "head of
    # department of X" query doesn't penalise the office-holder's profile chunk.
    if is_department_query(query) and not is_head_query(query):
        ds = department_relevance_score(document)
        score += ds if ds > 0 else -120.0

    score += admission_evidence_score(query, document)
    score += document_evidence_score(query, document)
    score += hostel_evidence_score(query, document)
    score += person_lookup_relevance_score(query, document) * 100.0
    score += course_relevance_score(query, document)
    score += club_relevance_score(query, document)
    score += activity_relevance_score(query, document)
    score += staff_relevance_score(query, document)

    if is_fee_query(query):
        fs = fee_evidence_score(query, document)
        score += fs if fs > 0 else -80.0
        if is_application_fee_query(query):
            score += 1800.0 if ("application fee" in d_norm or "application fees" in d_norm) else -120.0

    if is_attendance_query(query):
        score += attendance_relevance_score(document)

    if is_website_links_query(query) and "Website links found on this page" in document:
        score += 800.0

    if is_criteria_query(query):
        score += criteria_relevance_score(query, document)
        
    score += score_chunk_by_intent_and_entity(query, document, {})

    if is_table_of_contents_chunk(document) and "contents" not in q_norm:
        score -= 1200.0

    return max(score, 0.0)
