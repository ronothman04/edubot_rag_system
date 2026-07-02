from __future__ import annotations

"""
rag/intent.py
Query intent classification and entity extraction for St. Anthony's College EduBot.
Imports text_utils.py only.
"""

import re
from typing import Any

from .text_utils import (
    clean_text,
    fix_ocr_casing,
    normalize_query,
    normalize_text,
)

CASUAL_RESPONSES = {
    "hi":               "Hello! How can I help you with college-related information?",
    "hello":            "Hello! How can I help you with college-related information?",
    "hey":              "Hello! How can I help you with college-related information?",
    "good morning":     "Good morning! How can I help you with college-related information?",
    "good afternoon":   "Good afternoon! How can I help you with college-related information?",
    "good evening":     "Good evening! How can I help you with college-related information?",
    "thank you":        "You're very welcome! Is there anything else I can help you with about the college?",
    "thanks":           "You're very welcome! Is there anything else I can help you with about the college?",
    "thankyou":         "You're very welcome! Is there anything else I can help you with about the college?",
    "ok":               "Sounds good! Feel free to ask me anything else about the college.",
    "okay":             "Sounds good! Feel free to ask me anything else about the college.",
    "alright":          "Alright! I'm here whenever you have a question about the college.",
    "bye":              "Goodbye, and all the best! Feel free to come back anytime you need college-related information.",
    "goodbye":          "Goodbye, and all the best! Feel free to come back anytime you need college-related information.",
    "see you":          "See you! I'm always here if you have more questions about the college.",
}

COLLEGE_KEYWORDS = {
    "admission", "admissions", "apply", "application", "eligibility", "eligible",
    "course", "courses", "certificate", "programme", "program", "programmes", "programs",
    "fee", "fees", "semester", "hostel", "attendance", "exam", "examination",
    "marks", "documents", "migration", "transfer", "department", "departments",
    "hod", "faculty", "principal", "office", "contact", "college", "student",
    "subject", "subjects", "major", "minor", "syllabus", "scholarship", "library",
    "rules", "uniform", "timing", "class", "club", "clubs", "cell", "cells",
    "committee", "committees", "association", "associations", "society", "societies",
    "teacher", "teachers", "staff", "professor", "professors", "lecturer", "lecturers",
    "teaching", "teaching staff", "non teaching", "assistant professor", "associate professor",
    "faculty member", "faculty members", "head of department", "academic",
    "computer science", "computer application", "computer applications", "bca", "mca", "it",
    "information technology", "english", "economics", "commerce", "physics", "chemistry",
    "mathematics", "zoology", "botany", "biotechnology", "history", "political science",
    "sociology", "education", "mass communication", "media", "psychology",
    "activity", "activities", "student activities", "co-curricular", "co curricular",
    "extracurricular", "extra curricular", "events", "event", "seminar", "seminars",
    "workshop", "workshops", "guest lecture", "guest lectures", "industrial visit",
    "industrial visits", "annual fest", "debate", "debates", "sports", "cultural",
    "nss", "ncc",
}

HOMEWORK_PATTERNS = [
    "write my assignment", "do my assignment", "complete my assignment", "homework",
    "solve this homework", "write an essay", "essay on", "project report", "lab report",
    "answer this question for me", "give me assignment", "make assignment", "write notes on",
]

PERSONAL_SITUATION_PATTERNS = [
    "am i eligible", "can i apply", "can i get admission", "am i allowed", "can i join",
    "can i transfer", "i passed from", "i studied", "my marks", "my percentage", "i got",
    "i am from", "different college", "another college", "different board", "different university",
    "previous college", "previous university", "change my stream", "change subject",
    "failed", "fail", "compartment", "supplementary", "reappear", "back paper",
    "low marks", "less marks", "percentage", "marks",
]

VAGUE_COLLEGE_PATTERNS = {
    "admission", "admissions", "courses", "course", "fees", "fee", "documents",
    "hostel", "attendance", "exam", "examination", "college", "clubs", "club",
}

ROLE_QUERY_ALIASES: tuple[tuple[str, str], ...] = (
    ("vice principal", "vice principal"),
    ("principal", "principal"),
    ("head of department", "hod"),
    ("hod", "hod"),
    ("head", "hod"),
    ("assistant coordinator", "assistant coordinator"),
    ("coordinator", "coordinator"),
    ("vice chairman", "vice chairman"),
    ("vice chairperson", "vice chairperson"),
    ("chairman", "chairman"),
    ("chairperson", "chairperson"),
    ("secretary", "secretary"),
    ("hostel warden", "warden"),
    ("hall warden", "warden"),
    ("warden", "warden"),
    ("superintendent", "superintendent"),
    ("director", "director"),
    ("in charge", "in charge"),
    ("incharge", "in charge"),
)

PERSON_LOOKUP_TITLES = [
    "vice principal",
    "principal",
    "boys hostel warden",
    "girls hostel warden",
    "hostel warden",
    "warden",
    "hostel superintendent",
    "superintendent",
    "matron",
    "rector",
    "hostel in charge",
    "in charge",
    "head of department",
    "hod",
    "coordinator",
    "convenor",
    "convener",
    "secretary",
    "librarian",
    "director",
    "dean",
    "admission officer",
    "teacher in charge",
    "teacher-in-charge",
    "faculty in charge",
    "faculty-in-charge",
    "committee chairperson",
    "chairperson",
    "chairman",
    "chairwoman",
]

PERSON_LOOKUP_PATTERNS = [
    r"\bwho is\b",
    r"\bwho's\b",
    r"\bname of\b",
    r"\bwhat is the name of\b",
    r"\bwho are\b",
    r"\blist.*members\b",
    r"\bcontact person\b",
]

COURSE_ALIASES: dict[str, str] = {
    "b tech": "BTech",
    "btech": "BTech",
    "bca": "BCA",
    "mca": "MCA",
    "bba": "BBA",
    "mba": "MBA",
    "ba": "BA",
    "b a": "BA",
    "bsc": "BSc",
    "b sc": "BSc",
    "b com": "BCom",
    "bcom": "BCom",
    "m com": "MCom",
    "mcom": "MCom",
    "msc": "MSc",
    "m sc": "MSc",
    "ma": "MA",
    "m a": "MA",
    "pgdca": "PGDCA",
    "diploma": "Diploma",
    "nursing": "Nursing",
    "computer science": "Computer Science",
    "computer application": "Computer Application",
    "computer applications": "Computer Applications",
}

# Canonical degree-programme synonyms used for programme-availability verification.
# Keys are canonical programme codes; values list every spelling/abbreviation/full form
# that may appear in user queries OR in the college documents. Dot-tolerant matching is
# applied at lookup time, so "B.Tech" and "BTech" both resolve here.
PROGRAMME_SYNONYMS: dict[str, list[str]] = {
    "BTech": ["btech", "b tech", "bachelor of technology"],
    "BCA": ["bca", "bachelor of computer application", "bachelor of computer applications"],
    "MCA": ["mca", "master of computer application", "master of computer applications"],
    "BBA": ["bba", "bachelor of business administration"],
    "MBA": ["mba", "master of business administration"],
    "PGDCA": [
        "pgdca",
        "post graduate diploma in computer application",
        "post graduate diploma in computer applications",
    ],
    "BA": ["ba", "bachelor of arts"],
    "BSc": ["bsc", "b sc", "bachelor of science"],
    "BCom": ["bcom", "b com", "bachelor of commerce"],
    "MA": ["ma", "master of arts"],
    "MSc": ["msc", "m sc", "master of science"],
    "MCom": ["mcom", "m com", "master of commerce"],
}

# Human-friendly labels for the programme codes above (used in user-facing messages).
PROGRAMME_DISPLAY: dict[str, str] = {
    "BTech": "B.Tech",
    "BCA": "BCA",
    "MCA": "MCA",
    "BBA": "BBA",
    "MBA": "MBA",
    "PGDCA": "PGDCA",
    "BA": "B.A.",
    "BSc": "B.Sc.",
    "BCom": "B.Com.",
    "MA": "M.A.",
    "MSc": "M.Sc.",
    "MCom": "M.Com.",
}

SUBJECT_ALIASES: dict[str, str] = {
    "biology": "Biology",
    "botany": "Botany",
    "zoology": "Zoology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "mathematics": "Mathematics",
    "math": "Mathematics",
    "maths": "Mathematics",
    "commerce": "Commerce",
    "economics": "Economics",
    "english": "English",
    "history": "History",
    "political science": "Political Science",
    "political": "Political Science",
    "education": "Education",
    "sociology": "Sociology",
}

KNOWN_DEPARTMENT_NAMES = [
    "biochemistry", "biotechnology", "botany", "business administration", "chemistry",
    "commerce", "computer science", "economics", "education", "english",
    "environmental studies", "fishery science", "geology", "hindi", "history",
    "khasi", "mass media", "mathematics", "mizo", "music", "philosophy",
    "physics", "political science", "statistics", "value education", "zoology", "hospitality",
]

STAFF_KEYWORDS = {
    "teacher", "teachers", "teaching staff", "staff", "faculty", "faculty members", "faculty member",
    "professor", "professors", "lecturer", "lecturers", "assistant professor", "associate professor",
    "who teaches", "who are the teachers",
}

DEPARTMENT_TERMS = [
    "computer science", "computer applications", "computer application", "bca", "mca", "english",
    "economics", "commerce", "physics", "chemistry", "mathematics", "zoology", "botany",
    "biotechnology", "fishery science", "fishery", "fisheries", "history", "political science", "sociology", "education",
    "mass communication", "psychology", "business administration", "bba", "mba", "bcom", "mcom",
]

PERSONAL_ELIGIBILITY_CONDITIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("failed", "fail", "not passed"), "failed"),
    (("compartment",), "compartment"),
    (("supplementary",), "supplementary"),
    (("reappear", "back paper"), "reappear"),
    (("low marks", "less marks", "low percentage"), "low marks"),
    (("result pending", "awaiting result", "results pending"), "result pending"),
    (("gap year", "year gap", "gap-year"), "gap year"),
    (("another board", "different board"), "another board"),
    (("another university", "different university", "previous university"), "another university"),
    (("another college", "different college", "previous college", "transfer"), "another college"),
)

PROCEDURAL_QUERY_MARKERS = [
    "how to apply",
    "how to submit",
    "how to register",
    "how to get admission",
    "procedure",
    "application process",
    "admission process",
]

INTENT_PRIORITY = [
    "fees", "eligibility", "documents", "courses", "programme", 
    "department", "staff", "hostel", "attendance", "exam", 
    "admission", "contact", "facilities", "activity", "committee"
]

def detect_query_intents(query: str) -> list[str]:
    """Identify all relevant intents within a query."""
    intents = []
    if is_course_query(query): intents.append("courses")
    if is_department_query(query): intents.append("department")
    if is_fee_query(query): intents.append("fees")
    if is_eligibility_query(query): intents.append("eligibility")
    if is_contact_query(query): intents.append("contact")
    if is_facilities_query(query): intents.append("facilities")
    if is_hostel_query_local(query): intents.append("hostel")
    if is_attendance_query(query): intents.append("attendance")
    if is_exam_query(query): intents.append("exam")
    if is_document_query(query): intents.append("documents")
    if is_staff_query(query): intents.append("staff")
    if is_activity_query(query): intents.append("activity")
    if is_cell_or_committee_query(query): intents.append("committee")
    
    # Default to admission if "apply" or "process" is mentioned and no specific intent found
    if not intents and any(term in normalize_text(query) for term in ["admission", "apply", "application", "procedure"]):
        intents.append("admission")
        
    return intents or ["general"]

def get_primary_intent(intents: list[str]) -> str:
    """Determine the most specific intent to drive retrieval and answering."""
    for p_intent in INTENT_PRIORITY:
        if p_intent in intents:
            return p_intent
    return intents[0] if intents else "general"

def is_eligibility_query(query: str) -> bool:
    """Check if query is about criteria/eligibility."""
    q = normalize_text(query)
    return any(term in q for term in [
        "eligible", "eligibility", "criteria", "requirement", "qualification",
        "qualifying examination", "minimum qualification", "required subject",
        "required subjects", "marks", "percentage",
    ])

def is_exam_query(query: str) -> bool:
    """Check if query is about examinations."""
    q = normalize_query(query)
    if "qualifying examination" in q and not any(
        term in q for term in ["exam rules", "examination rules", "sessional", "internal assessment", "test"]
    ):
        return False
    return any(term in q for term in ["exam", "examination", "sessional", "internal assessment", "test"])

def is_document_query(query: str) -> bool:
    """Check if query is about required documents."""
    q = normalize_text(query)
    return any(term in q for term in ["document", "documents", "certificate", "marksheet", "admit card"])

def is_hostel_query_local(query: str) -> bool:
    """Check if query is about hostel."""
    q = normalize_query(query)
    return any(term in q for term in [
        "hostel", "accommodation", "residence", "residential", "warden", "hall",
    ])

def extract_entities(query: str) -> dict[str, str | None]:
    """Extract department, course, or specific topics from the query."""
    q = normalize_query(query)
    
    # Extract department
    dept = extract_department_from_query(query)
    
    # Extract course
    course = extract_target_course_from_query(query)
    
    # Extract specific topic (e.g. "attendance", "scholarship")
    topic = extract_exact_topic(query)
    
    return {
        "department": dept,
        "course": course,
        "topic": topic
    }


def is_personal_record_query(query: str) -> bool:
    q = query.lower()
    patterns = ["my fee", "my attendance", "my marks", "my result", "my grade", "my schedule", "my classes"]
    return any(p in q for p in patterns)

def is_homework_or_assignment(query: str) -> bool:
    """Check if query is homework helper request."""
    q = normalize_query(query)
    return any(pattern in q for pattern in HOMEWORK_PATTERNS)


def is_personal_situation_question(query: str) -> bool:
    """Check if query refers to personal candidate qualifications/marks/percentage."""
    q = normalize_query(query)
    return any(pattern in q for pattern in PERSONAL_SITUATION_PATTERNS)


def is_website_links_query(query: str) -> bool:
    """Check if query asks specifically for links/URLs/downloads/student corner."""
    q = normalize_text(query)
    link_terms = [
        "quick links", "quick link", "useful links", "important links",
        "college website links", "website links", "student links",
        "student corner", "downloads", "download links", "notices",
        "notice links", "admission links",
    ]
    if any(term in q for term in link_terms):
        return True
    return ("link" in q or "links" in q) and "website" in q


def is_college_related(query: str) -> bool:
    """Check if query is college-oriented based on keyword sets."""
    q = normalize_query(query)
    words = set(q.split())
    if words & COLLEGE_KEYWORDS:
        return True
    return any(keyword in q for keyword in COLLEGE_KEYWORDS if " " in keyword)


def is_clearly_out_of_scope(query: str) -> bool:
    """Check if query falls into general knowledge or non-college questions."""
    q = normalize_query(query)
    out_of_scope_phrases = [
        "prime minister", "president of india", "president of the united states",
        "tell me a joke", "weather", "weather today", "weather forecast",
        "cricket score", "cricket world cup", "football score", "world cup",
        "ipl", "olympics", "fifa", "movie review", "stock price", "share price",
        "bitcoin price", "crypto price", "recipe", "how to cook", "horoscope",
        "celebrity gossip", "current news", "news today", "latest news",
        "capital of", "population of", "currency of", "national anthem of",
        "meaning of life", "translate", "write a poem", "write me a poem",
        "write a song", "write a story", "compose a", "lyrics",
    ]
    if any(phrase in q for phrase in out_of_scope_phrases):
        return True
    # General-knowledge question forms — only out of scope when the query carries
    # no college signal at all (so e.g. "who won the inter-college match" is kept).
    gk_patterns = [
        "who won", "who is the ceo", "what is the capital", "how far is",
        "distance between", "who invented", "who discovered", "how to make",
    ]
    if not is_college_related(q) and any(p in q for p in gk_patterns):
        return True
    return False


def is_vague_college_question(query: str) -> bool:
    """Check if query is extremely vague (e.g. single word like 'admission')."""
    q = normalize_query(query)
    if not q:
        return False
    if any(pattern in q for pattern in ["is there", "do you have", "does the college have", "are there", "available"]):
        return False
    if "hostel" in q and any(term in q for term in [
        "admission", "application", "form", "apply", "rules", "fee", "fees",
        "warden", "eligibility", "eligible", "documents", "procedure", "process",
    ]):
        return False
    if q in VAGUE_COLLEGE_PATTERNS:
        return True
    words = q.split()
    if len(words) > 4:
        return False
    detail_markers = {
        "required", "requirement", "requirements", "criteria", "eligible", "eligibility",
        "process", "how", "what", "which", "when", "where", "who", "why", "list",
        "structure", "rules", "rule", "fee", "fees", "syllabus", "syllabi", "dates", "date",
        "procedure", "procedures", "contact", "address", "phone", "email", "timings", "timing",
    }
    if any(marker in words for marker in detail_markers):
        return False
    
    # Only treat as vague if it consists purely of vague patterns and/or minor words
    minor_words = {"the", "a", "an", "for", "in", "on", "at", "to", "of", "and", "or", "about"}
    if all(w in VAGUE_COLLEGE_PATTERNS or w in minor_words for w in words):
        return True
        
    return False


def is_contact_query(query: str) -> bool:
    """Check if query is looking for telephone numbers, emails, addresses."""
    q = normalize_query(query)
    if is_website_links_query(query):
        return False
    if any(word in q for word in ["committee", "cell", "department", "club", "quick link", "quick links", "student corner"]):
        return False
    contact_terms = [
        "contact", "email", "mail", "phone", "mobile", "telephone",
        "address", "location", "located", "fax", "helpline", "office number"
    ]
    if any(term in q for term in contact_terms):
        return True
    if any(phrase in q for phrase in [
        "reach the college", "reach college", "reach the office",
        "get in touch", "contact the college", "contact college",
    ]):
        return True
    return bool(re.search(r"\bph\b", q))


def is_facilities_query(query: str) -> bool:
    """Check for campus facility/amenity requests."""
    q = normalize_query(query)
    return any(term in q for term in [
        "facility", "facilities", "amenity", "amenities", "campus services",
        "campus infrastructure",
    ])


def is_department_query(query: str) -> bool:
    """Check if query mentions department(s)."""
    return any(word in normalize_query(query) for word in ["department", "departments"])


def is_head_query(query: str) -> bool:
    """Check if query is looking for leading figures (head, HOD, warden, coordinator)."""
    q = normalize_query(query)
    return bool(re.search(
        r"\b(head|hod|director|incharge|principal|vice principal|chairman|chairperson|secretary|coordinator|warden|superintendent)\b"
        r"|in\s+charge|hostel\s+warden|hall\s+warden",
        q,
    ))


def extract_query_entities(query: str) -> dict[str, Any]:
    """Extract dynamic role and target from the query sentence."""
    q = clean_text(query)
    role_patterns = [
        r"\bwho\s+is\s+the\s+(.+?)\s+of\s+(.+?)(?:\?|$)",
        r"\bwho\s+are\s+the\s+(.+?)\s+of\s+(.+?)(?:\?|$)",
        r"\b(.+?)\s+of\s+(.+?)(?:\?|$)",
    ]
    for pattern in role_patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            role = clean_text(match.group(1)).strip(" .:-")
            target = clean_text(match.group(2)).strip(" .:-")
            if len(role) >= 3 and len(target) >= 3:
                return {
                    "intent": "role_lookup",
                    "role": role,
                    "target": target,
                }
    return {
        "intent": "general",
        "role": None,
        "target": None,
    }


def is_person_lookup_query(query: str) -> bool:
    """Check if query looks up names of administrative or hostel heads."""
    q = normalize_query(query)
    has_lookup_phrase = any(re.search(pattern, q) for pattern in PERSON_LOOKUP_PATTERNS)
    has_title = any(title in q for title in PERSON_LOOKUP_TITLES)
    has_name_request = bool(re.search(r"\bname\b", q))
    implied_role_lookup = bool(re.search(
        r"\b(?:hod|head of department|department head|principal|warden|coordinator)\b"
        r"\s+(?:of|for|in)\s+",
        q,
    ))
    return has_title and (has_lookup_phrase or has_name_request or implied_role_lookup)


def get_requested_person_title(query: str) -> str:
    """Extract which title is requested in person lookup."""
    q = (query or "").lower()
    for title in sorted(PERSON_LOOKUP_TITLES, key=len, reverse=True):
        if title in q:
            return title
    return ""


def _clean_role_target(value: str) -> str | None:
    """Clean the extracted role target block."""
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9\s&.'-]", " ", value)
    value = re.split(
        r"\b(role|name designation|authorities|office bearers|members|no name designation|required subject|qualifying examination|departments faculty|teaching staff)\b",
        value,
        maxsplit=1,
    )[0]
    value = re.sub(
        r"\b(the|a|an|name|of|for|in|at|college|department|dept|who|is|are|members?|head|hod)\b",
        " ",
        value,
    )
    value = re.sub(r"\s+", " ", value).strip(" .:-")
    return value or None


def extract_role_query(query: str) -> dict[str, str | None]:
    """Identify if role keyword matches ROLE_QUERY_ALIASES and extract target."""
    q = normalize_query(query)
    q = re.sub(r"[^a-z0-9\s&.'?-]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        return {"role": None, "target": None}

    role_pattern = "|".join(
        re.escape(alias)
        for alias, _role in sorted(ROLE_QUERY_ALIASES, key=lambda item: -len(item[0]))
    )
    patterns = [
        rf"\b(?:who\s+is|who\s+are|name\s+of)\s+(?:the\s+)?({role_pattern})(?:\s+of\s+(.+?))?(?:\?|$)",
        rf"\b({role_pattern})\s+of\s+(.+?)(?:\?|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        raw_role = match.group(1)
        target = _clean_role_target(match.group(2) if len(match.groups()) > 1 and match.group(2) else "")
        for alias, role in ROLE_QUERY_ALIASES:
            if normalize_query(alias) == normalize_query(raw_role):
                return {"role": role, "target": target}

    for alias, role in ROLE_QUERY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return {"role": role, "target": None}

    return {"role": None, "target": None}


def is_broad_department_list_query(query: str) -> bool:
    """Check if query is asking to list all/available departments."""
    q = normalize_text(query)
    if not is_department_query(q) or is_head_query(q):
        return False
    return any(marker in q for marker in [
        "list", "different", "available", "all", "what departments", "which departments", "show departments",
    ])


def is_course_query(query: str) -> bool:
    """Check if a query requests programmes or curricular content.

    ``subject`` by itself is ambiguous (it also occurs in faculty profiles and
    eligibility prose), so it is treated as curriculum only when paired with a
    list/semester/programme signal.  Strong curricular nouns such as syllabus,
    curriculum, paper and module are independently sufficient.
    """
    q = normalize_query(query)
    if any(word in q for word in [
        "course", "courses", "program", "programs", "programme", "programmes",
        "degree", "degrees", "ug", "undergraduate", "pg", "postgraduate", "diploma", "certificate",
        "vtc", "vocational", "vocational training", "vocational course",
        "syllabus", "syllabi", "curriculum", "curricula", "paper", "papers",
        "module", "modules",
    ]):
        return True

    has_subject = bool(re.search(r"\bsubjects?\b", q))
    has_curriculum_scope = bool(re.search(
        r"\b(semester|sem|first|second|third|fourth|fifth|sixth|seventh|eighth|"
        r"bca|mca|bba|mba|bsc|msc|bcom|mcom|ba|ma|bachelor|master|degree)\b",
        q,
    ))
    has_list_form = bool(re.search(
        r"\b(what|which|list|show|all|available)\b|\bare\s+there\b",
        q,
    ))
    return has_subject and (has_curriculum_scope or has_list_form)


def is_postgraduate_course_query(query: str) -> bool:
    """Check if query is specifically for PG (postgraduate) courses."""
    q = normalize_text(query)
    return is_course_query(query) and any(term in q for term in [
        "pg", "postgraduate", "post graduate", "post graduation", "master", "masters", "m a", "m sc", "m com", "mca", "pgdca",
    ])


def is_certificate_course_query(query: str) -> bool:
    """Check if query is for professional add-on/certificate courses."""
    q = normalize_text(query)
    return "certificate" in q and ("course" in q or "courses" in q)


def is_fee_query(query: str) -> bool:
    """Check if query mentions fee details."""
    q = normalize_query(query)
    return any(word in q for word in ["fee", "fees", "payment", "payments", "charges"])


def is_fee_table_query(query: str) -> bool:
    """Check if query looks for complete semester or admission fee structures."""
    if not is_fee_query(query):
        return False
    q = normalize_text(query)
    return any(marker in q for marker in [
        "structure", "list", "all", "different", "breakdown", "table", "details", "fee details", "fees details",
    ])


def is_application_fee_query(query: str) -> bool:
    """Check if query is about the registration/application fee amount."""
    q = normalize_text(query)
    return "application" in q and is_fee_query(query)


def is_criteria_query(query: str) -> bool:
    """Check if query is about subject selection criteria (major, minor, MDC, SEC)."""
    q = normalize_text(query)
    return "criteria" in q and any(marker in q for marker in [
        "choosing", "choose", "selecting", "selection", "major", "minor", "mdc", "vac", "sec", "aec",
    ])


def is_club_query(query: str) -> bool:
    """Check if query mentions clubs or societies."""
    q = normalize_text(query)
    return any(term in q for term in ["club", "clubs", "association", "associations", "society", "societies"])


def is_cell_or_committee_query(query: str) -> bool:
    """Check if query mentions committees or administrative cells."""
    q = normalize_query(query)
    return any(term in q for term in ["cell", "cells", "committee", "committees"])


def is_activity_query(query: str) -> bool:
    """Check if query refers to events, NCC, NSS, seminars, sports, fests."""
    q = normalize_text(query)
    return any(term in q for term in [
        "activity", "activities", "student activities",
        "co curricular", "co-curricular", "extracurricular", "extra curricular",
        "events", "event", "seminar", "seminars", "workshop", "workshops",
        "guest lecture", "guest lectures", "industrial visit", "industrial visits",
        "annual fest", "debate", "debates", "sports", "cultural", "nss", "ncc",
    ])


def is_list_query(query: str) -> bool:
    """Identify if query seeks listing structures rather than single cell lookups."""
    q = normalize_text(query)
    list_words = [
        "list", "available", "all", "everything", "entire", "complete", "full",
        "what are", "which are", "show", "summarize", "summarise", "summary",
        "what clubs", "what cells", "what committees", "what courses",
        "courses are there", "clubs are there", "what departments", "which departments",
        "show departments", "different", "breakdown", "table", "details",
    ]
    has_list_marker = any(word in q for word in list_words)
    if is_course_query(query) and re.search(
        r"\b(?:what|which)\s+(?:subjects?|courses?|papers?|modules?)\s+are\s+there\b|"
        r"\b(?:subjects?|courses?|papers?|modules?)\s+(?:are\s+)?(?:there|available|offered)\b|"
        r"\b(?:what|which)\s+(?:vocational\s+training\s+)?courses?\s+are\s+offered\b",
        q,
    ):
        has_list_marker = True
    if is_staff_query(query) and re.search(
        r"\bwho\s+(?:teaches?|are\s+the\s+(?:faculty|teachers?|staff))\b",
        q,
    ):
        has_list_marker = True
    has_generic_list_intent = ("list" in q or "all" in q) and any(term in q for term in ["rule", "rules", "guideline", "guidelines", "requirement", "requirements", "eligibility", "document", "documents", "fee", "fees", "course", "courses", "department", "departments", "hostel", "hostels"])
    return (
        is_broad_department_list_query(query)
        or is_fee_table_query(query)
        or is_website_links_query(query)
        or (is_course_query(query) and has_list_marker)
        or (is_criteria_query(query) and has_list_marker)
        or (is_club_query(query) and has_list_marker)
        or (is_cell_or_committee_query(query) and has_list_marker)
        or (is_activity_query(query) and has_list_marker)
        or (is_hostel_query(query) and has_list_marker)
        or (is_staff_query(query) and has_list_marker)
        or (is_contact_query(query) and has_list_marker)
        or (is_facilities_query(query) and has_list_marker)
        or (is_attendance_query(query) and has_list_marker)
        or has_generic_list_intent
    )



def is_attendance_query(query: str) -> bool:
    """Check if query refers to attendance regulations."""
    q = normalize_query(query)
    return bool(re.search(r"\b(attendance|attend|attending|absence|absent)\b", q)) or (
        "classes" in q and any(term in q for term in ["how many", "minimum", "required", "must"])
    )


def is_specific_query(query: str) -> bool:
    """Check if query is specific and has clear scoping terms."""
    q = normalize_text(query)
    specific_markers = [
        "who is", "who are", "members of", "member of", "head of", "coordinator of",
        "chairman of", "principal of", "director of", "rules of", "guidelines of",
        "email", "contact", "phone", "address", "does college have", "does the college have", "is there",
    ]
    if any(marker in q for marker in specific_markers):
        return True
    if len(q.split()) <= 5 and any(word in q for word in [
        "committee", "cell", "department", "rules", "guidelines", "hostel", "library",
        "attendance", "iqac", "ragging", "exam", "examination",
    ]):
        return True
    return False


def is_document_overview_query(query: str) -> bool:
    """Check if query wants a whole document summary or overview."""
    q = normalize_text(query)
    return any(marker in q for marker in [
        "all data", "all information", "everything", "entire document", "full document",
        "complete document", "summarize document", "summary of document",
        "what is in document", "what is in the document",
    ])


def has_personal_situation_context(query: str, context: str) -> bool:
    """Cross reference user context request words with retrieved text."""
    q = normalize_query(query)
    c = normalize_text(context)
    if not c:
        return False
    if any(m in q for m in ["another college", "different college", "previous college", "transfer"]):
        return any(m in c for m in [
            "transfer certificate", "migration certificate", "previous college",
            "another college", "different college", "transfer student",
        ])
    if any(m in q for m in ["different university", "previous university"]):
        return any(m in c for m in ["migration certificate", "previous university", "different university", "university"])
    if any(m in q for m in ["different board", "board"]):
        return any(m in c for m in ["recognized board", "board of secondary education", "certificate"])
    if any(m in q for m in ["my marks", "my percentage", "i got"]):
        return any(m in c for m in ["marks", "percentage", "cut off", "merit", "counselling"])
    return any(m in c for m in ["eligibility", "eligible", "admission criteria", "requirements"])


def is_staff_query(query: str) -> bool:
    """Check if query is asking about teachers/faculty members."""
    q = normalize_query(query)
    return any(term in q for term in STAFF_KEYWORDS)


def extract_department_from_query(query: str) -> str | None:
    """Extract which department name exists in query."""
    q = normalize_query(query)
    for dept in DEPARTMENT_TERMS:
        if dept in q:
            return dept
    return None


def extract_staff_department_from_query(query: str) -> str | None:
    """Detect which academic department the user refers to for staff inquiries."""
    dept = extract_department_from_query(query)
    if dept:
        return dept

    entities = extract_query_entities(query)
    role = normalize_text(str(entities.get("role") or ""))
    target = normalize_text(str(entities.get("target") or ""))
    if target and any(term in role for term in ["faculty", "staff", "teacher", "professor", "lecturer"]):
        return target

    q = normalize_text(query)
    for known_dept in KNOWN_DEPARTMENT_NAMES:
        if known_dept in q:
            return known_dept

    return None


def chunk_has_staff_evidence(text: str) -> bool:
    """Verify if the chunk has faculty or HOD lists."""
    t = normalize_text(text)
    markers = [
        "faculty members", "faculty member", "assistant professor",
        "associate professor", "lecturer",
        "department faculty", "hod", "head of department", "head ug", "director pg",
    ]
    teaching_staff = bool(re.search(r"(?<!non )\bteaching staff\b", t))
    repeated_professors = len(re.findall(r"\bprof(?:essor)?\.?\b", t)) >= 2
    return teaching_staff or repeated_professors or any(m in t for m in markers)


def chunk_looks_like_course_only(text: str) -> bool:
    """Identify if the chunk lists subject structures/syllabus without listing staff names."""
    t = normalize_text(text)
    course_markers = [
        "disciplines for fyu", "disciplines for fy", "courses offered",
        "programme structure", "program structure", "subject combination",
        "major subject", "minor subject", "syllabus", "semester",
    ]
    return any(m in t for m in course_markers) and not chunk_has_staff_evidence(t)


def _clean_extracted_topic(topic: str) -> str | None:
    """Clean the extracted topic text helper."""
    topic = normalize_text(topic)
    if not topic:
        return None
    topic = re.sub(
        r"\b(the|a|an|college|document|details|detail|information|info|members|member)\b",
        " ", topic,
    )
    topic = re.sub(r"\s+", " ", topic).strip()
    if len(topic) < 3 or topic in {"of", "about", "for", "from"}:
        return None
    return topic


def extract_topic_from_query(query: str) -> str | None:
    """Extract topic keywords based on regex triggers."""
    q = normalize_text(query)
    if not q:
        return None
    patterns = [
        r"\bdoes\s+(?:the\s+)?college\s+have\s+(.+)$",
        r"\bis\s+there\s+(.+)$",
        r"\b(?:head|hod|director|coordinator|chairman|principal|incharge)\s+(?:of|for)\s+(.+)$",
        r"\bin\s+charge\s+(?:of|for)\s+(.+)$",
        r"\bmembers?\s+(?:of|in)\s+(.+)$",
        r"\b(?:rules|guidelines|fees?|admission|eligibility|attendance|contact)\s+(?:of|for|in)\s+(.+)$",
        r"\b(?:about|regarding|for)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            topic = _clean_extracted_topic(match.group(1))
            if topic:
                return topic
    return None


# TODO: split
def extract_exact_topic(query: str) -> str | None:
    """Check query against a static checklist of high confidence topics."""
    q = normalize_text(query)

    topic_patterns = [
        "vice principal", "vice-principal", "principal", "chairman", "chairperson",
        "vice chairman", "vice chairperson", "secretary", "coordinator",
        "assistant coordinator", "college authorities", "administration",
        "governing body", "registrar",

        # Committees / cells
        "website committee", "wellness committee", "library committee",
        "sports committee", "canteen committee", "admission committee",
        "anti ragging committee", "anti substance abuse committee",
        "disciplinary committee", "disciplinary security committee",
        "examination committee", "institutional collaboration committee",
        "institutional ethics for biological research", "media and publications committee",
        "mentor and mentee committee", "time table committee",
        "grievance redressal committee", "scholarships committee",
        "students representatives election committee",
        "green initiative waste management committee",
        "college students uniform committee", "convocation committee",
        "cultural committee", "disaster management covid response committee",
        "education tour committee", "literary committee", "inter faith committee",
        "iso certification committee", "rangers rovers coordination committee",
        "remedial classes committee", "rusa implementation committee",
        "ncc coordination committee", "nss coordination committee", "iqac",
        "anti sexual harassment cell", "counselling cell", "equal opportunity cell",
        "first aid and medical cell", "research and consultancy cell", "sacmis cell",

        # Clubs
        "english theatre club", "commerce club", "club", "clubs",

        # Departments
        "computer science", "biochemistry", "biotechnology", "botany",
        "business administration", "chemistry", "commerce", "economics",
        "education", "english", "environmental studies", "fishery science",
        "geology", "hindi", "history", "khasi", "mass media", "mathematics",
        "mizo", "music", "philosophy", "physics", "political science",
        "statistics", "value education", "zoology", "hospitality",

        # Sections / topics
        "certificate courses", "hostel rules", "library guidelines",
        "computer lab guidelines", "attendance and leave requirements",
        "attendance requirements", "attendance requirement", "minimum attendance",
        "shortage of attendance", "attendance", "dress code",
        "common minimum decency", "semester fee payment", "fee payment", "ragging",
        "general guidelines and rules", "semester examinations", "university examinations",
        "contact information",
        "criteria for choosing a major subject", "criteria for choosing a minor subject",
        "criteria for choosing mdc", "criteria for choosing vac",
        "criteria for choosing sec", "criteria for choosing aec",
    ]

    for topic in topic_patterns:
        if topic in q:
            return topic

    return extract_topic_from_query(query)


PERSONAL_ELIGIBILITY_CONDITIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("failed", "fail", "not passed"), "failed"),
    (("compartment",), "compartment"),
    (("supplementary",), "supplementary"),
    (("reappear", "back paper"), "reappear"),
    (("low marks", "less marks", "low percentage"), "low marks"),
    (("result pending", "awaiting result", "results pending"), "result pending"),
    (("gap year", "year gap", "gap-year"), "gap year"),
    (("another board", "different board"), "another board"),
    (("another university", "different university", "previous university"), "another university"),
    (("another college", "different college", "previous college", "transfer"), "another college"),
)


def _normalize_course_candidate(value: str) -> str | None:
    candidate = normalize_query(value)
    candidate = re.sub(
        r"\b(can|i|am|eligible|apply|for|in|to|join|take|get|admission|into|the|a|an|course|programme|program)\b",
        " ",
        candidate,
    )
    candidate = re.sub(r"\s+", " ", candidate).strip()

    if not candidate:
        return None

    for alias, display in sorted(COURSE_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", candidate):
            return display

    if len(candidate.split()) <= 4 and candidate not in {"hostel", "fees", "documents", "admission"}:
        return candidate.title()

    return None


def extract_target_course_from_query(query: str) -> str | None:
    original = str(query or "")
    q = normalize_query(original)

    for alias, display in sorted(COURSE_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return display

    for alias, display in sorted(SUBJECT_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return display

    phrase_patterns = [
        r"(?:apply|eligible|admission|join|get into|take admission)\s+(?:for|in|to|into)?\s+([a-z][a-z0-9 .+-]{1,60})",
        r"(?:can i|get|am i)\s+(?:apply|eligible|get admission|join)\s+(?:for|in|to|into)?\s+([a-z][a-z0-9 .+-]{1,60})",
    ]

    for pattern in phrase_patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        value = re.split(
            r"\b(if|when|with|after|because|and|or|but|can|should|what|how|who|where|why)\b",
            match.group(1),
            maxsplit=1,
        )[0]
        course = _normalize_course_candidate(value)
        if course and normalize_query(course) not in {"hostel", "accommodation"}:
            return course

    return None


def _squash_dots(text: str) -> str:
    """Normalize text and drop dots so 'B.Tech' == 'BTech' and 'B. Sc' == 'B Sc'."""
    t = normalize_text(text).replace(".", "")
    return re.sub(r"\s+", " ", t).strip()


def detect_programme(query: str) -> str | None:
    """
    Return the canonical programme code (e.g. 'BCA', 'BTech') if the query names a
    known degree programme, else None. Dot/space tolerant ('B.Tech', 'b tech', 'BTECH').
    Used by the programme-availability verification gate to prevent hallucinated programmes.
    """
    q = _squash_dots(query)
    # Match longer synonyms first to avoid short codes (e.g. 'ba') shadowing 'bba'.
    ordered = sorted(
        ((code, syn) for code, syns in PROGRAMME_SYNONYMS.items() for syn in syns),
        key=lambda item: -len(item[1]),
    )
    for code, syn in ordered:
        needle = syn.replace(".", "")
        if re.search(rf"\b{re.escape(needle)}\b", q):
            return code
    return None


def programme_grounded_in_docs(programme: str, docs: list[str]) -> bool:
    """
    True if the programme (any of its synonyms/full forms) actually appears in the
    retrieved document chunks. This is the evidence check that decides whether the
    chatbot is allowed to answer about a specific programme.
    """
    if not programme or not docs:
        return False
    blob = _squash_dots("\n".join(d for d in docs if d))
    for syn in PROGRAMME_SYNONYMS.get(programme, [programme.lower()]):
        needle = syn.replace(".", "")
        if re.search(rf"\b{re.escape(needle)}\b", blob):
            return True
    return False


def is_programme_availability_query(query: str) -> bool:
    """True if the user is explicitly asking whether a programme is available/offered."""
    q = normalize_text(query)
    return any(
        phrase in q
        for phrase in [
            "available", "is there", "do you have", "does the college have",
            "does the college offer", "offer", "offered", "offers", "provide",
            "is it offered", "is it available",
        ]
    )


def is_programme_specific_query(query: str) -> bool:
    """
    True if the query is actionable about a specific programme (availability,
    admission, eligibility, fees, seats, etc.). Used to scope the programme gate so
    it never fires on unrelated questions.
    """
    q = normalize_text(query)
    triggers = [
        "admission", "admit", "admitted", "apply", "application",
        "eligib", "eligible", "criteria", "qualification", "qualifications",
        "available", "offer", "offered", "offers", "provide", "provides",
        "join", "get into", "take admission", "fee", "fees", "seat", "seats",
        "course", "courses", "programme", "programmes", "program", "programs",
        "is there", "do you have", "does the college",
    ]
    return any(t in q for t in triggers)


# Umbrella/general degrees the college offers across many subject specializations.
# Unlike standalone professional programmes (BTech, BCA, MBA…), a bare query about
# one of these ("eligibility for BA") is answerable from the general admission
# policy even when the exact degree token isn't in the top-reranked chunks — so the
# programme gate must NOT refuse it as "not offered".
UMBRELLA_DEGREES: set[str] = {"BA", "BSc", "BCom", "MA", "MSc", "MCom"}


def query_names_subject(query: str) -> bool:
    """True if the query names a specific subject/department (e.g. 'BA English')."""
    q = normalize_text(query)
    for alias in SUBJECT_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return True
    for dept in KNOWN_DEPARTMENT_NAMES:
        if re.search(rf"\b{re.escape(dept)}\b", q):
            return True
    return False


def is_bare_umbrella_degree_query(query: str) -> bool:
    """True when the query names a bare umbrella degree (BA/BSc/…) with no specific
    subject. Such queries are answerable from general admission policy, so the
    programme-not-found gate should be bypassed for them."""
    programme = detect_programme(query)
    if programme not in UMBRELLA_DEGREES:
        return False
    return not query_names_subject(query)


def extract_subject_from_personal_query(query: str) -> str | None:
    q = normalize_query(query)

    for pattern in [
        r"(?:failed|fail|compartment|supplementary|reappear|not passed|back paper)\s+(?:in\s+)?([a-z][a-z ]{1,40})",
        r"(?:in\s+)([a-z][a-z ]{1,40})\s+(?:failed|fail|compartment|supplementary|reappear|not passed)",
    ]:
        match = re.search(pattern, q)
        if not match:
            continue
        value = re.split(
            r"\b(can|could|should|apply|eligible|admission|join|for|in|to|and|or|but)\b",
            match.group(1),
            maxsplit=1,
        )[0].strip()
        for alias, display in sorted(SUBJECT_ALIASES.items(), key=lambda item: -len(item[0])):
            if re.search(rf"\b{re.escape(alias)}\b", value):
                return display
        if value:
            return value.title()

    for alias, display in sorted(SUBJECT_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return display

    return None


def extract_personal_eligibility_case(query: str) -> dict[str, Any]:
    q = normalize_query(query)

    condition = None
    for triggers, label in PERSONAL_ELIGIBILITY_CONDITIONS:
        if any(trigger in q for trigger in triggers):
            condition = label
            break

    asks_admission = any(term in q for term in [
        "apply", "admission", "eligible", "eligibility", "join", "get into", "take admission",
    ])
    is_hostel_only = any(term in q for term in ["hostel", "accommodation", "warden", "hall"]) and not any(
        term in q for term in ["course", "programme", "program", "subject"]
    )
    target_course = None if is_hostel_only else extract_target_course_from_query(query)
    subject = extract_subject_from_personal_query(query)

    return {
        "is_personal_eligibility": bool(asks_admission and not is_hostel_only),
        "target_course": target_course,
        "subject": subject,
        "condition": condition,
    }


# TODO: split
def classify_admission_query(query: str) -> dict[str, Any]:
    """
    Generic admission-query understanding.
    This extracts intent and entities only; it never encodes final college facts.
    """
    q = normalize_query(query)
    target_course = extract_target_course_from_query(query)
    subject = extract_subject_from_personal_query(query)
    role_case = extract_role_query(query)

    condition = None
    for triggers, label in PERSONAL_ELIGIBILITY_CONDITIONS:
        if any(trigger in q for trigger in triggers):
            condition = label
            break

    asks_personal = bool(re.search(r"\b(can i|am i|i have|i got|my |i failed|i passed|i studied|i am)\b", q))
    missing_details: list[str] = []

    category = "general_college"
    if role_case.get("role") or is_head_query(query):
        category = "role_person"
    elif is_contact_query(query) or any(term in q for term in ["admission office", "contact admission", "phone number", "email"]):
        category = "contact"
    elif any(term in q for term in ["hostel admission", "apply for hostel", "hostel during admission"]):
        category = "hostel_admission"
    elif any(term in q for term in ["reservation", "reserved", "quota", "category", "caste", "income", "domicile"]):
        category = "reservation"
    elif any(term in q for term in ["merit", "selection", "selected", "cutoff", "cut off", "waiting list", "entrance test"]):
        category = "merit_selection"
    elif is_fee_query(query):
        category = "fees"
    elif any(term in q for term in ["document", "documents", "certificate", "certificates", "marksheet", "admit card", "original"]):
        category = "documents"
    elif any(term in q for term in ["eligible", "eligibility", "low marks", "failed", "compartment", "supplementary", "reappear", "result pending", "gap year", "another board", "another university", "another college"]):
        category = "personal_eligibility" if asks_personal or condition else "eligibility"
    elif is_course_query(query):
        category = "courses"
    elif any(term in q for term in ["last date", "deadline", "start", "open now", "admission open", "when will admission"]):
        category = "admission_dates"
    elif any(term in q for term in ["form", "online", "offline", "where can i get", "application form"]):
        category = "admission_form"
    elif any(term in q for term in ["admission", "apply", "application", "procedure", "process", "counselling"]):
        category = "admission_process"

    if category == "personal_eligibility" and not target_course:
        missing_details.append("course/programme")
    if category == "fees" and not target_course and not any(term in q for term in ["application", "admission", "semester", "hostel", "laboratory", "structure"]):
        missing_details.append("course/semester/fee type")
    if category == "documents" and not any(term in q for term in ["admission", "hostel", "exam", "examination", "migration", "transfer", "original"]):
        missing_details.append("purpose")

    return {
        "category": category,
        "target_course": target_course,
        "subject": subject,
        "condition": condition,
        "missing_details": missing_details,
        "role": role_case.get("role"),
        "target": role_case.get("target"),
        "is_personal": category == "personal_eligibility",
    }


def classify_query_intent(query: str) -> str:
    """Classify user query into specialized structural pipeline routes."""
    q = normalize_text(query)

    if is_homework_or_assignment(query):
        return "homework"

    if is_website_links_query(query):
        return "website_links"

    if is_contact_query(query):
        return "contact"

    if is_attendance_query(query):
        return "attendance"

    if is_application_fee_query(query):
        return "application_fee"

    if is_fee_table_query(query):
        return "fee_table"

    if is_criteria_query(query):
        return "criteria"

    if is_certificate_course_query(query):
        return "certificate_courses"

    if is_activity_query(q):
        return "activity_list"

    if is_website_links_query(query):
        return "website_links"

    if is_club_query(query):
        return "club_list"

    if is_cell_or_committee_query(query):
        if any(term in q for term in ["member", "members", "who", "coordinator", "chairman", "chairperson", "secretary"]):
            return "committee_members"
        return "committee_list"

    if is_staff_query(query):
        return "staff"

    if is_warden_query(query):
        return "warden"

    if is_head_query(query):
        return "role_lookup"

    if is_broad_department_list_query(query):
        return "department_list"

    if is_course_query(query):
        return "course_list"

    return "general"


def is_hostel_query(query: str) -> bool:
    """Check if query is about the hostel facility."""
    q = normalize_query(query)
    return any(term in q for term in [
        "hostel", "accommodation", "residence", "residential", "hosteller",
        "boys hostel", "girls hostel",
    ])


def is_procedural_query(query: str) -> bool:
    """Check if query concerns procedural issues (how to apply/register)."""
    q = normalize_text(query)
    return any(marker in q for marker in PROCEDURAL_QUERY_MARKERS)


def is_warden_query(query: str) -> bool:
    """Check if query is looking for the hostel warden."""
    q = normalize_text(query)
    return any(
        term in q
        for term in ["warden", "hostel warden", "hall warden", "superintendent"]
    )


def extract_hostel_target_from_query(query: str) -> str | None:
    """Extract which hostel block (e.g. Stephen Hall) is target of query."""
    q = clean_text(query)
    patterns = [
        r"warden\s+of\s+(.+?)(?:\?|$)",
        r"hostel\s+warden\s+of\s+(.+?)(?:\?|$)",
        r"hall\s+warden\s+of\s+(.+?)(?:\?|$)",
        r"superintendent\s+of\s+(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            target = clean_text(match.group(1))
            target = re.sub(
                r"\b(the|college|warden|superintendent)\b", " ", target, flags=re.IGNORECASE,
            )
            target = re.sub(r"\bstephan\s+hall\b", "Stephen Hall", target, flags=re.IGNORECASE)
            target = re.sub(r"\s+", " ", target).strip(" .:-")
            if normalize_text(target) == "stephen hall":
                target = "Stephen Hall"
            if len(target) >= 3:
                return target
    return None


def extract_query_target(query: str) -> dict[str, Any]:
    """Parse entities to find the topic category and targeting keywords."""
    q = normalize_query(query)
    role_case = extract_role_query(query)
    role = role_case.get("role")
    target = _clean_query_target(role_case.get("target"))

    category = str(classify_admission_query(query).get("category") or "general_college")
    if category == "role_person":
        if "department" in q or "dept" in q or role in {"hod", "head"}:
            category = "department"
        elif any(term in q for term in ["committee", "cell"]):
            category = "committee"

    if not target:
        patterns = [
            r"\b(?:fee|fees|application fee)\s+(?:for|of|in)\s+(.+?)(?:\?|$)",
            r"\b(?:eligibility|eligible|criteria)\s+(?:for|of|in)\s+(.+?)(?:\?|$)",
            r"\b(?:documents?|certificates?)\s+(?:required\s+)?(?:for|of|in)\s+(.+?)(?:\?|$)",
            r"\b(?:rules?|guidelines)\s+(?:for|of|in)\s+(.+?)(?:\?|$)",
            r"\b(?:courses?|programmes?|programs?)\s+(?:for|of|in)\s+(.+?)(?:\?|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, q)
            if match:
                target = _clean_query_target(match.group(1))
                break

    if not target:
        target = _clean_query_target(extract_target_course_from_query(query) or extract_topic_from_query(query))

    if any(term in q for term in ["committee", "cell"]):
        category = "committee"
        if not target:
            m = re.search(r"\b([a-z][a-z\s&'-]{2,80}\s+(?:committee|cell))\b", q)
            target = _clean_query_target(m.group(1)) if m else target
    elif any(term in q for term in ["hostel", "warden", "hall", "accommodation"]):
        category = "hostel"
        if not target and "rules" in q:
            target = "hostel rules"
    elif is_fee_query(query):
        category = "fee"
    elif is_course_query(query):
        category = "course"
    elif any(term in q for term in ["documents", "certificate", "marksheet"]):
        category = "documents"
    elif any(term in q for term in ["eligibility", "eligible", "criteria"]):
        category = "eligibility"
    elif is_contact_query(query):
        category = "contact"
    elif any(term in q for term in ["admission", "application"]):
        category = "admission"

    if target and "committee" in q and "committee" not in target:
        target = f"{target} committee"
    if target and "cell" in q and "cell" not in target:
        target = f"{target} cell"

    result = {"role": role, "target": target, "category": category}
    return result


def _display_department_name(department: str | None) -> str | None:
    if not department:
        return None
    dept = fix_ocr_casing(clean_text(department)).strip(" .:-")
    if not dept:
        return None
    dept_norm = normalize_text(dept)
    if dept_norm in KNOWN_DEPARTMENT_NAMES:
        return dept_norm.title()
    return dept


def _dept_aliases(dept: str) -> list[str]:
    """Return a set of normalized surface forms for a department name."""
    aliases = [dept]
    if "computer science" in dept:
        aliases += ["computer sc", "comp sci", "cs department", "dept of computer"]
    if "computer application" in dept:
        aliases += ["comp app", "bca", "mca", "dept of computer app"]
    if "english" in dept:
        aliases += ["dept of english", "english department"]
    if "economics" in dept:
        aliases += ["dept of economics", "economics department"]
    if "fishery" in dept:
        aliases += ["fishery science", "fisheries", "department of fishery science", "fishery department"]
    if "business administration" in dept or "bba" in dept:
        aliases += ["bba", "business administration", "department of business administration", "dept of business administration"]
    if "commerce" in dept or "bcom" in dept or "mcom" in dept:
        aliases += ["bcom", "mcom", "commerce", "department of commerce", "dept of commerce"]
    return aliases


# TODO: split
def staff_relevance_score(query: str, document: str, meta: dict | None = None) -> float:
    if not is_staff_query(query):
        return 0.0

    d_norm = normalize_text(document)
    score = 0.0

    if chunk_has_staff_evidence(document):
        score += 350.0
    if "teaching staff" in d_norm:
        score += 700.0
    if "department of" in d_norm:
        score += 160.0
    if chunk_looks_like_course_only(document):
        score -= 900.0

    dept = extract_staff_department_from_query(query)
    if dept:
        aliases = _dept_aliases(normalize_text(dept))
        has_dept = any(alias and alias in d_norm for alias in aliases)
        if has_dept:
            score += 1400.0
            if "teaching staff" in d_norm:
                score += 1800.0
        else:
            score -= 350.0

    if any(term in d_norm for term in ["committee", "cell"]) and "department of" not in d_norm:
        score -= 450.0

    section = normalize_text(str((meta or {}).get("section_title", "") or ""))
    if dept and any(alias and alias in section for alias in _dept_aliases(normalize_text(dept))):
        score += 800.0

    return score


def expand_person_lookup_query(query: str) -> str:
    title = get_requested_person_title(query)
    if not title:
        return query
    return (
        query
        + " "
        + title
        + " hostel warden name of warden warden name "
        + "staff name faculty name designation contact administration "
        + "hostel superintendent matron rector in charge "
        + "boys hostel warden girls hostel warden"
    )


def build_role_retrieval_query(query: str) -> str:
    role_case = extract_role_query(query)
    role = role_case.get("role")
    target = role_case.get("target")

    if not role:
        return query

    parts = [
        query,
        role,
        f"{role} name",
        f"{role} designation",
        "name designation office bearers authorities members",
    ]

    if role == "hod":
        parts.extend(["head of department", "head", "hod name designation"])

    if target:
        parts.extend([
            target,
            f"{target} {role}",
            f"{target} members",
            f"{target} office bearers",
        ])

    return " ".join(part for part in parts if part)


def build_staff_retrieval_query(query: str) -> str:
    base_query = (query or "").strip()
    dept = extract_staff_department_from_query(base_query)
    parts = [
        base_query,
        "teaching staff faculty teachers professor lecturer assistant professor associate professor name designation",
    ]
    if dept:
        parts.append(dept)
        parts.append(f"Department of {dept}")
    return " ".join(parts)


def build_generic_retrieval_query(original_query: str) -> str:
    """
    Expand by category and extracted entities, not by institution-specific answers.
    """
    info = classify_admission_query(original_query)
    additions_by_category: dict[str, list[str]] = {
        "admission_process": [
            "admission application eligibility criteria prospectus documents form merit selection entrance test counselling admission process admission procedure registration notification notice",
        ],
        "admission_dates": [
            "admission application eligibility criteria prospectus documents form merit selection entrance test counselling admission date last date deadline start admission open notification notice academic calendar",
        ],
        "admission_form": [
            "admission application eligibility criteria prospectus documents form merit selection entrance test counselling admission form application form online application offline application registration form where to apply",
        ],
        "eligibility": [
            "admission application eligibility criteria prospectus documents form merit selection entrance test counselling qualifying examination required subjects minimum marks percentage",
        ],
        "personal_eligibility": [
            "admission eligibility criteria target course required subjects qualifying examination minimum marks passed condition application prospectus",
        ],
        "courses": [
            "courses programmes offered admission undergraduate postgraduate certificate diploma degree subjects",
        ],
        "documents": [
            "documents required admission documents certificates marksheet admit card transfer certificate migration certificate character certificate original documents photocopy application",
        ],
        "fees": [
            "fee fees fee structure admission fee application fee semester fee refundable payment instalment installment online offline charges",
        ],
        "merit_selection": [
            "merit list selection admission merit entrance test cutoff cut off waiting list counselling selected notification notice",
        ],
        "reservation": [
            "reservation quota category caste income domicile certificate admission eligibility",
        ],
        "hostel_admission": [
            "hostel admission hostel application form submit warden parent guardian prospectus boys hostel girls hostel admission procedure hostel rules hostel eligibility hostel fees documents accommodation hosteller room hall superintendent",
        ],
        "contact": [
            "admission office contact phone telephone mobile email address website office principal",
        ],
        "role_person": [
            "role role name name designation authorities office bearers administration members no name designation",
        ],
        "general_college": [
            "college information official resources prospectus notice",
        ],
    }

    parts: list[str] = [original_query]
    parts.extend(additions_by_category.get(str(info.get("category")), []))

    if info.get("target_course"):
        course = str(info["target_course"])
        parts.extend([
            course,
            f"{course} admission eligibility",
            f"{course} eligibility criteria",
            f"{course} required subjects",
            f"{course} qualifying examination",
            f"{course} minimum marks",
            f"{course} passed",
        ])
    if info.get("subject"):
        subject = str(info["subject"])
        parts.extend([
            subject,
            f"{subject} required subject qualifying examination pass",
        ])
    if info.get("condition"):
        parts.append(f"{info['condition']} required subjects qualifying examination minimum marks passed eligibility criteria admission")
    if info.get("role"):
        role = str(info["role"])
        parts.extend([role, f"{role} name", f"{role} designation"])
    if info.get("target"):
        target = str(info["target"])
        parts.extend([target, f"{target} members", f"{target} office bearers"])

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = normalize_query(part)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return " ".join(deduped)


def detect_intent(query: str) -> dict:
    """
    Goal 6: Query Intent Detection
    Return dict with intent string and extracted entities list.
    """
    intents = detect_query_intents(query)
    primary = get_primary_intent(intents)
    entities_dict = extract_entities(query)
    
    # Flatten entities into a list as requested
    entities_list = []
    for k, v in entities_dict.items():
        if isinstance(v, list):
            entities_list.extend(v)
        elif v:
            entities_list.append(v)
            
    # Also extract exact topic/role targets
    exact = extract_exact_topic(query)
    if exact and exact not in entities_list:
        entities_list.append(exact)
        
    return {
        "intent": primary,
        "entities": [str(e) for e in entities_list if e]
    }


# Apply lru_cache to all query intent classifiers dynamically to speed up CPU loops
from functools import lru_cache

_cached_bool_funcs = [
    "is_eligibility_query", "is_exam_query", "is_document_query", "is_hostel_query_local",
    "is_personal_record_query", "is_homework_or_assignment", "is_personal_situation_question",
    "is_website_links_query", "is_college_related", "is_clearly_out_of_scope",
    "is_vague_college_question", "is_contact_query", "is_department_query", "is_head_query",
    "is_person_lookup_query", "is_broad_department_list_query", "is_course_query",
    "is_postgraduate_course_query", "is_certificate_course_query", "is_fee_query",
    "is_fee_table_query", "is_application_fee_query", "is_criteria_query", "is_club_query",
    "is_cell_or_committee_query", "is_activity_query", "is_list_query", "is_attendance_query",
    "is_specific_query", "is_document_overview_query", "is_staff_query", "is_warden_query"
]

_cached_str_funcs = [
    "get_requested_person_title", "extract_exact_topic", "extract_topic_from_query",
    "extract_staff_department_from_query", "extract_department_from_query",
    "extract_target_course_from_query", "extract_subject_from_personal_query",
    "extract_hostel_target_from_query"
]

_cached_dict_funcs = [
    "extract_entities", "extract_query_entities", "extract_role_query",
    "classify_admission_query", "extract_personal_eligibility_case"
]

_cached_list_funcs = [
    "detect_query_intents"
]

for name in _cached_bool_funcs + _cached_str_funcs:
    if name in globals() and callable(globals()[name]):
        globals()[name] = lru_cache(maxsize=512)(globals()[name])

for name in _cached_dict_funcs:
    if name in globals() and callable(globals()[name]):
        orig_func = globals()[name]
        def _dict_wrapper(fn=orig_func):
            @lru_cache(maxsize=512)
            def _tuple_cached(q):
                res = fn(q)
                return tuple(res.items()) if isinstance(res, dict) else res
            return lambda q: dict(_tuple_cached(q))
        globals()[name] = _dict_wrapper()

for name in _cached_list_funcs:
    if name in globals() and callable(globals()[name]):
        orig_func = globals()[name]
        def _list_wrapper(fn=orig_func):
            @lru_cache(maxsize=512)
            def _tuple_cached(q):
                res = fn(q)
                return tuple(res) if isinstance(res, list) else res
            return lambda q: list(_tuple_cached(q))
        globals()[name] = _list_wrapper()
