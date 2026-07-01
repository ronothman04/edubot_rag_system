from __future__ import annotations

"""
rag/query_expansion.py
Query expansion mappings, smart keyword retrieval builders, and followup handling for EduBot RAG.
Imports intent.py and text_utils.py only at module level.
"""

import re
from difflib import get_close_matches
from typing import Any

from .intent import (
    CASUAL_RESPONSES,
    extract_personal_eligibility_case,
    extract_query_entities,
    extract_role_query,
    extract_exact_topic,
    is_homework_or_assignment,
    detect_query_intents,
    get_primary_intent,
    extract_entities,
    is_personal_situation_question,
    is_website_links_query,
    is_college_related,
    is_clearly_out_of_scope,
    is_vague_college_question,
    is_contact_query,
    is_department_query,
    is_head_query,
    is_course_query,
    is_postgraduate_course_query,
    is_certificate_course_query,
    is_fee_query,
    is_fee_table_query,
    is_application_fee_query,
    is_criteria_query,
    is_club_query,
    is_cell_or_committee_query,
    is_activity_query,
    is_list_query,
    is_attendance_query,
    is_specific_query,
    is_document_overview_query,
    is_staff_query,
    is_hostel_query,
    is_procedural_query,
    is_warden_query,
    is_person_lookup_query,
    get_requested_person_title,
    extract_staff_department_from_query,
    extract_department_from_query,
    classify_admission_query,
)
from .text_utils import (
    clean_text,
    important_words,
    normalize_query,
    normalize_query_text,
    normalize_text,
)

QUERY_EXPANSIONS: dict[str, str] = {
    # Common college document vocabulary
    "apply": "admission application form registration applicant eligibility documents",
    "application": "admission application form registration applicant prospectus",
    "admission": "admission admissions apply application form procedure eligibility documents dates",
    "admissions": "admission admissions apply application form procedure eligibility documents dates",
    "eligibility": "eligible eligibility criteria admission qualification marks percentage",
    "documents": "documents required certificates migration transfer character marksheet admit card",
    "prospectus": "prospectus handbook college rules admission courses fees departments",
    "office": "office administrative office contact phone email address principal vice principal",
    "contact": "contact address phone telephone mobile email website office fax",
    "fee": "fee fees fee structure tuition payment charges amount hostel fee admission fee",
    "fees": "fee fees fee structure tuition payment charges amount hostel fee admission fee",
    "attendance": "attendance minimum attendance percentage rules regular classes absentee",
    "exam": "exam examination semester evaluation marking scheme tests grading rules conduct",
    "examination": "exam examination semester evaluation marking scheme tests grading rules conduct",
    "principal": "principal vice principal administration college authorities",
    "hod": "head hod head of department department faculty teaching staff",
    "faculty": "faculty teaching staff assistant professor associate professor lecturer department",
    "staff": "staff teaching staff non teaching faculty department designation",

    # Departments
    "department": (
        "departments department of academic departments department list "
        "academic disciplines degree programmes faculty teaching staff"
    ),
    "departments": (
        "departments department of academic departments department list "
        "academic disciplines degree programmes faculty teaching staff"
    ),

    # Committees / cells
    "committee": (
        "committee committees cell members name designation chairman vice chairman "
        "coordinator assistant coordinator principal member"
    ),
    "committees": (
        "committee committees cell members name designation chairman vice chairman "
        "coordinator assistant coordinator principal member"
    ),
    "cell":   "cells clubs committees associations societies student activities members coordinator",
    "cells":  "cells clubs committees associations societies student activities members coordinator",

    # Clubs / associations / societies
    "club":          "clubs cells committees associations societies student activities extracurricular co-curricular",
    "clubs":         "clubs cells committees associations societies student activities extracurricular co-curricular",
    "student clubs": "clubs cells committees associations societies student activities extracurricular co-curricular",
    "association":   "associations clubs cells societies student activities",
    "associations":  "associations clubs cells societies student activities",
    "society":       "societies clubs cells associations student activities",
    "societies":     "societies clubs cells associations student activities",

    # Courses / programmes
    "course": (
        "courses programmes programs academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses certificate courses "
        "programmes offered by the college BA BSc BCom BBA MA MSc MCA PGDCA degree honours general"
    ),
    "courses": (
        "courses programmes programs academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses certificate courses "
        "programmes offered by the college BA BSc BCom BBA MA MSc MCA PGDCA degree honours general"
    ),
    "certificate course": (
        "certificate courses UGC approved career oriented courses professional certificate courses "
        "add-on courses addon courses skill courses computer applications"
    ),
    "certificate courses": (
        "certificate courses UGC approved career oriented courses professional certificate courses "
        "add-on courses addon courses skill courses computer applications"
    ),
    "program":    (
        "programmes programs courses academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses offered by the college"
    ),
    "programs":   (
        "programmes programs courses academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses offered by the college"
    ),
    "programme":  (
        "programmes programs courses academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses offered by the college"
    ),
    "programmes": (
        "programmes programs courses academic programmes undergraduate degree programs "
        "postgraduate courses professional courses diploma courses offered by the college"
    ),
    "ug":           "under graduate undergraduate UG degree programmes courses BA BSc BCom BBA",
    "undergraduate":"under graduate undergraduate UG degree programmes courses BA BSc BCom BBA",
    "pg":           "post graduate postgraduate PG programmes courses MA MSc MCA PGDCA Master",
    "postgraduate": "post graduate postgraduate PG programmes courses MA MSc MCA PGDCA Master",

    # Admission / eligibility
    "admission":             "admission procedure requirements eligibility application documents form submit office warden parent guardian merit counselling",
    "am i eligible":         "admission eligibility criteria requirements qualification marks percentage",
    "eligible":              "admission eligibility criteria requirements qualification marks percentage",
    "eligibility":           "admission eligibility criteria requirements qualification marks percentage",
    "can i apply":           "admission application process application form submit eligibility criteria requirements",
    "can i get admission":   "admission eligibility criteria requirements application process application form submit",
    "how to apply":          "admission application process application form submit office principal warden parent guardian documents required eligibility",
    "how to submit":         "application form submit submitted office principal warden parent guardian documents required admission",
    "how to register":       "registration application form submit office admission process eligibility documents required",
    "how to get admission":  "admission process admission procedure application form submit office principal documents required eligibility",
    "procedure":             "procedure process steps application form submit office principal warden parent guardian documents required eligibility",
    "application process":   "application process application form submit office principal warden parent guardian documents required eligibility",
    "admission process":     "admission process admission procedure application form submit office principal documents required eligibility",
    "another college":       "transfer student migration certificate admission eligibility previous college",
    "different college":     "transfer student migration certificate admission eligibility previous college",
    "different board":       "migration certificate admission eligibility board certificate",
    "different university":  "migration certificate transfer admission eligibility university",
    "transfer":              "transfer certificate migration certificate previous college admission",
    "migration":             "migration certificate transfer admission previous university",

    # Subject choice / criteria
    "criteria":   "criteria choosing choose selection requirement requirements eligibility major minor subject course",
    "choosing":   "criteria choosing choose selection requirement requirements eligibility major minor subject course",
    "major subject": (
        "criteria for choosing a major subject major subject selection subject choice "
        "major course main focus in-depth study admission CUET subject eligibility"
    ),
    "choosing a major subject": "criteria for choosing a major subject subject selection major subject choice",

    # Fees / facilities / rules
    "fee":          "fee fees semester fee payment instalment fine application fee laboratory charges",
    "fees":         "fee fees semester fee payment instalment fine application fee laboratory charges",
    "hostel":       "hostel admission hostel application form submit warden parent guardian prospectus boys hostel girls hostel admission procedure hostel rules hostel eligibility hostel fees",
    "hostel admission": "hostel admission hostel application form submit warden parent guardian prospectus boys hostel girls hostel admission procedure hostel rules hostel eligibility hostel fees",
    "hostel form": "hostel application form hostel admission form submit warden parent guardian prospectus boys hostel girls hostel hostel eligibility",
    "hostel application": "hostel application form hostel admission submit warden parent guardian prospectus boys hostel girls hostel hostel eligibility",
    "boys hostel": "boys hostel hostel admission hostel application form submit warden parent guardian hostel prospectus hostel rules hostel eligibility",
    "girls hostel": "girls hostel hostel admission hostel application form submit warden parent guardian hostel prospectus hostel rules hostel eligibility",
    "warden": "warden hostel warden hall warden hostel superintendent name designation hostel hall",
    "hostel warden": "hostel warden warden hall warden hostel superintendent name designation hostel hall",
    "hall warden": "hall warden hostel warden warden hostel superintendent name designation hostel hall",
    "hostel superintendent": "hostel superintendent hostel warden hall warden name designation hostel hall",
    "library":      "college library guidelines books issue fine silence identity card",
    "attendance": (
        "attendance minimum attendance required attendance requirement attendance requirements "
        "minimum 75 percent 75% classes leave requirements regular attendance shortage of attendance "
        "eligible examination eligibility examination minimum classes"
    ),
    "minimum attendance": (
        "attendance minimum attendance required attendance requirement attendance requirements "
        "minimum 75 percent 75% classes shortage of attendance eligible examination eligibility examination"
    ),
    "dress code": "dress code common minimum decency clothes boys girls prohibited",
    "uniform":    "dress code common minimum decency clothes boys girls prohibited",
    "ragging":    "UGC regulations curbing ragging punishment anti ragging",
    "exam":       "examination instructions candidates semester university examinations",
    "exams":      "examination instructions candidates semester university examinations",
    "contact":    "contact information address phone email website principal college office",
    "email":      "email address mail contact information college office principal",
    "phone":      "phone mobile telephone contact information college office principal",
    "address":    "address contact information college office principal",

    # Activities
    "activity": "co-curricular extension activities student activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "activities": "co-curricular extension activities student activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "college activities": "student activities co-curricular extension activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "student activities": "student activities co-curricular extension activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "co-curricular": "co-curricular co curricular extension activities student activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "co curricular": "co-curricular co curricular extension activities student activities clubs ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "extension activities": "extension activities co-curricular student activities ncc nss rovers rangers sac-seva social outreach seminars workshops guest lectures sports cultural",
    "extracurricular": "extracurricular extra curricular activities student activities clubs societies associations events seminars workshops sports cultural nss ncc",
    "events": "events student activities annual fest seminars workshops guest lectures industrial visits debates sports cultural nss ncc",
    "placement": "placement placements career guidance career counselling student development services sds coaching workshops employability",
    "placements": "placement placements career guidance career counselling student development services sds coaching workshops employability",
    "career guidance": "career guidance placement assistance student development services sds coaching workshops personal educational career guidance",
    "facilities": "facilities campus facilities laboratories library wifi hostel counselling medical aid ambulance sports gymnasium canteen bank atm",

    # Faculty / staff
    "teacher":         "faculty teaching staff professor lecturer department academic designation",
    "teachers":        "faculty teaching staff professor lecturer department academic designation",
    "teaching staff":  "faculty teachers professor lecturer department designation",
    "staff":           "faculty teaching staff professor lecturer department academic designation",
    "faculty":         "teachers teaching staff professor lecturer department academic designation",
    "professor":       "faculty teaching staff lecturer academic department designation",
    "professors":      "faculty teaching staff lecturer academic department designation",
    "lecturer":        "faculty teaching staff professor academic department designation",
    "lecturers":       "faculty teaching staff professor academic department designation",
    "hod":             "head of department department head faculty",
    "head of department": "hod department head faculty",

    # College authority roles
    "vice principal":       "vice principal vice-principal principal administration college authorities designation name",
    "vice-principal":       "vice principal vice-principal principal administration college authorities designation name",
    "principal":            "principal vice principal vice-principal college authorities administration designation name",
    "chairman":             "chairman chairperson committee cell members name designation principal coordinator",
    "vice chairman":        "vice chairman vice chairperson committee cell members name designation",
    "chairperson":          "chairman chairperson committee cell members name designation principal coordinator",
    "secretary":            "secretary governing body committee cell members name designation",
    "coordinator":          "coordinator committee cell members name designation assistant coordinator",
    "assistant coordinator":"assistant coordinator coordinator committee cell members name designation",
    "members":              "members committee cell no name designation chairman coordinator assistant coordinator",
    "member":               "member members committee cell no name designation chairman coordinator assistant coordinator",
    "college authorities":  "principal vice principal vice-principal secretary governing body administration designation name",
    "governing body":       "governing body principal secretary chairman members designation name",

    # Common departments / courses
    "computer science":        "department of computer science computer applications bca mca faculty teachers staff",
    "computer application":    "department of computer applications bca mca faculty teachers staff",
    "computer applications":   "department of computer applications bca mca faculty teachers staff",
    "bca":                     "bachelor of computer applications bachelor of computer application computer science department",
    "mca":                     "master of computer applications master of computer application computer science department",
    "it":                      "information technology department faculty teachers",
    "information technology":  "it information technology department faculty teachers",
}

SMART_RETRIEVAL_INTENTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("admission", "admissions", "apply", "application", "join", "eligible", "eligibility"),
        "admission eligibility criteria application process qualification requirements prospectus",
    ),
    (
        ("failed", "fail", "compartment", "supplementary", "reappear", "back paper", "low marks", "percentage", "marks"),
        "eligibility criteria qualifying examination passed failed compartment supplementary reappear marks percentage minimum qualification admission",
    ),
    (
        ("fee", "fees", "pay", "payment", "amount", "cost", "charges", "joining"),
        "fee structure admission fee semester fee application fee payment amount charges prospectus",
    ),
    (
        ("hostel", "accommodation", "stay", "far away", "distance", "warden", "hall"),
        "hostel admission hostel application form submit warden parent guardian prospectus boys hostel girls hostel hostel rules hostel eligibility hostel fees accommodation hosteller room hall superintendent residence",
    ),
    (
        ("how to apply", "how to submit", "how to register", "how to get admission", "procedure", "application process", "admission process"),
        "application form submit submitted office warden principal admission parent guardian documents required eligibility admission procedure application process",
    ),
    (
        ("attendance", "attend", "absence", "absent", "leave", "classes", "regularly", "shortage"),
        "attendance minimum attendance shortage absence leave requirements classes regularity rules",
    ),
    (
        ("exam", "examination", "semester", "internal", "assessment", "test", "promotion"),
        "examination semester internal assessment tests promotion rules guidelines",
    ),
    (
        ("document", "documents", "certificate", "certificates", "bring", "marksheet", "migration", "transfer"),
        "documents required certificates admission marksheet migration transfer character certificate required documents",
    ),
    (
        ("contact", "office", "phone", "email", "address", "call", "reach"),
        "contact information college office phone email address admission office principal",
    ),
    (
        ("course", "courses", "programme", "programmes", "program", "subject", "subjects", "stream", "computer"),
        "courses programmes subjects undergraduate postgraduate certificate course department computer science computer application",
    ),
    (
        ("department", "departments", "faculty", "hod", "head", "principal", "staff", "teacher", "professor", "lecturer"),
        "departments faculty head of department hod principal teaching staff designation",
    ),
    (
        ("club", "clubs", "activity", "activities", "sports", "nss", "ncc", "event", "events", "cultural"),
        "student activities clubs sports nss ncc events co-curricular extracurricular cultural seminars workshops",
    ),
    (
        ("committee", "committees", "cell", "cells", "member", "members", "coordinator", "chairman"),
        "committees cells members coordinator chairman chairperson secretary designation",
    ),
    (
        ("rule", "rules", "guideline", "guidelines", "allowed", "permission", "discipline"),
        "rules guidelines discipline permission college regulations student conduct",
    ),
)

FORMAT_FOLLOWUP_PATTERNS = [
    "short answer", "make it short", "shorter", "summarize", "summarise", "in short",
    "answer in", "bullet points", "make it bullet", "make it simple", "simple answer",
    "simplify", "brief", "briefly", "concise",
]

DETAIL_FOLLOWUP_PATTERNS = [
    "explain more", "tell me more", "more details", "give more details",
    "elaborate", "explain in detail", "details", "expand", "expand it",
]

REFERENCE_FOLLOWUP_PATTERNS = ["that", "this", "it", "above", "previous", "same", "what about"]


# TODO: split
def build_smart_eligibility_retrieval_query(query: str) -> str:
    """Strengthen retrieval for personal eligibility questions."""
    case = extract_personal_eligibility_case(query)

    if not case["is_personal_eligibility"]:
        return query

    target_course = case.get("target_course")
    subject = case.get("subject")
    condition = case.get("condition")

    additions: list[str] = [
        query,
        "admission",
        "eligibility",
        "eligibility criteria",
        "qualifying examination",
        "minimum marks",
        "required subjects",
        "subject combination",
        "undergraduate",
    ]

    if target_course:
        t = str(target_course)
        additions.extend([
            t,
            f"{t} admission",
            f"{t} eligibility",
            f"{t} admission eligibility",
            f"{t} required subjects",
            f"{t} subject combination",
            f"{t} undergraduate",
            f"Department of {t}",
            f"qualifying examination for {t}",
            f"minimum marks for {t}",
            "eligibility criteria",
        ])

        science_subjects = {
            "Botany", "Zoology", "Chemistry", "Physics", "Mathematics", "Statistics",
            "Biology", "Biotechnology", "Geology", "Fishery Science",
        }
        if subject in science_subjects or t in {"BSc", "BTech"}:
            additions.append(f"BSc {subject}" if subject else "BSc")

    if subject:
        s = str(subject)
        additions.extend([
            s,
            f"{s} admission",
            f"{s} eligibility",
            f"{s} required subjects",
            f"{s} subject combination",
            f"Department of {s}",
            "qualifying examination",
            "minimum marks",
            "eligibility criteria",
            f"required subject {s}",
        ])

        science_subjects = {
            "Botany", "Zoology", "Chemistry", "Physics", "Mathematics", "Statistics",
            "Biology", "Biotechnology", "Geology", "Fishery Science",
        }
        if s in science_subjects:
            additions.extend(["BSc", f"BSc {s}"])

    if condition:
        additions.append(f"{condition} compartment supplementary reappear failed pass eligibility")

    return " ".join(str(part) for part in additions if part)


def build_smart_retrieval_query(query: str) -> str:
    """Intelligently route and build target query mapping for RAG."""
    base_query = (query or "").strip()
    q_norm = normalize_query(base_query)
    
    intents = detect_query_intents(base_query)
    primary = get_primary_intent(intents)
    entities = extract_entities(base_query)
    
    additions: list[str] = [base_query]
    
    # Handle Department/Course context
    entity_context = ""
    if entities["department"]: entity_context += f" {entities['department']}"
    if entities["course"]: entity_context += f" {entities['course']}"
    
    # Intent-based additions
    intent_map = {
        "courses": "courses offered programmes undergraduate postgraduate subjects",
        "admission": "admission process application procedure form registration portal",
        "eligibility": "eligibility criteria minimum marks qualification requirements",
        "fees": "fee structure admission fee semester fee payment",
        "contact": "contact phone email admission office principal reception",
        "hostel": "hostel admission rules fees warden accommodation",
        "documents": "documents required certificates marksheet migration transfer",
        "staff": "teaching staff faculty professor lecturer hod",
        "attendance": "attendance percentage rules regular classes leave",
        "exam": "examination internal assessment sessional tests",
        "department": "departments list name academic departments degree programmes course list",
        "committee": "committee committees cells members list chairman coordinator",
        "activity": "activities sports events games clubs student corner",
    }
    
    # Expand for each detected intent, focusing on the primary one
    for intent in intents:
        expansion = intent_map.get(intent, "")
        if expansion:
            # Attach entity to the intent expansion for better relevance
            if entity_context:
                additions.append(f"{expansion}{entity_context}")
            else:
                additions.append(expansion)
                
    # Specific high-priority expansion for person lookup
    if "staff" in intents or is_person_lookup_query(base_query):
        additions.append("name designation office bearers authorities members")

    # Personal eligibility logic
    if "eligibility" in intents and is_personal_situation_question(base_query):
        additions.append(build_smart_eligibility_retrieval_query(base_query))

    # Fallback to important words
    additions.extend(important_words(base_query))

    deduped: list[str] = []
    seen: set[str] = set()

    # Order by specificity: entities + primary intent first
    priority_parts = [base_query]
    if entity_context: priority_parts.append(entity_context)

    for part in priority_parts + additions:
        cleaned = normalize_query(part)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)

    return " ".join(deduped)


# TODO: split
def smart_clarification_response(query: str) -> dict[str, Any] | None:
    """Detect if clarification is required due to ambiguous or missing entities."""
    from .schemas import make_response

    q = normalize_query(query)
    admission_info = classify_admission_query(query)
    admission_category = str(admission_info.get("category") or "")

    if not is_college_related(query):
        return None

    if admission_category in {
        "admission_process", "admission_dates", "admission_form", "documents",
        "merit_selection", "reservation", "hostel_admission", "contact", "role_person",
    }:
        return None

    eligibility_case = extract_personal_eligibility_case(query)
    if admission_category == "personal_eligibility" or eligibility_case["is_personal_eligibility"]:
        if eligibility_case["target_course"]:
            return None
        return make_response(
            "I can check admission or eligibility from the uploaded college resources, "
            "but please mention the course/programme you want to apply for.",
            suggestions=[
                "What are the eligibility criteria for admission?",
                "What courses are available for admission?",
                "What documents are required for admission?",
            ],
            response_type="clarification",
            retrieval_query=query,
        )

    if any(term in q for term in ["hostel", "accommodation", "warden", "hall"]) and any(
        term in q for term in ["admission", "rules", "fees", "fee", "warden", "documents", "eligible", "eligibility"]
    ):
        return None

    course_detail = bool(re.search(
        r"\b(undergraduate|postgraduate|bachelor|master|ba|bsc|bcom|bba|bca|ma|msc|mcom|mca|certificate|course|programme|program)\b",
        q,
    ))
    subject_detail = any(subject in q for subject in [
        "computer", "english", "economics", "commerce", "physics", "chemistry",
        "mathematics", "zoology", "botany", "biotechnology", "history",
        "political science", "sociology", "education", "mass communication",
    ])
    short_or_broad = len(q.split()) <= 6

    answer = ""
    suggestions: list[str] = []

    if any(term in q for term in ["admission", "apply", "eligible", "eligibility", "join", "failed", "compartment", "supplementary", "reappear", "low marks", "percentage"]):
        if (course_detail or subject_detail) and not short_or_broad:
            return None
        answer = (
            "I can check admission or eligibility from the uploaded college resources, "
            "but please mention the course/programme you want to apply for."
        )
        suggestions = [
            "What are the eligibility criteria for admission?",
            "What documents are required for admission?",
            "What courses are available for admission?",
        ]
    elif any(term in q for term in ["fee", "fees", "pay", "payment", "amount", "charges"]):
        if any(term in q for term in ["application", "semester", "laboratory", "hostel", "admission"]) or course_detail or subject_detail:
            return None
        answer = (
            "I can check fee details from the uploaded college resources, but please mention "
            "the course, semester, or fee type."
        )
        suggestions = [
            "What is the application fee?",
            "What is the semester fee structure?",
            "What are the laboratory charges?",
        ]
    elif any(term in q for term in ["hostel", "accommodation", "stay", "warden", "hall"]):
        if any(term in q for term in ["admission", "rules", "fees", "fee", "warden", "documents", "eligible", "eligibility"]):
            return None
        if any(pattern in q for pattern in ["is there", "do you have", "does the college have", "are there", "available", "facility", "facilities"]):
            return None
        answer = (
            "I can check hostel information from the uploaded college resources. "
            "Please specify whether you mean hostel admission, rules, fees, documents, or warden details."
        )
        suggestions = [
            "What are the hostel rules?",
            "Who is eligible for hostel admission?",
            "Who is the hostel warden?",
        ]
    elif any(term in q for term in ["document", "documents", "certificate", "certificates", "bring"]):
        if any(term in q for term in ["admission", "examination", "exam", "hostel", "migration", "transfer"]):
            return None
        answer = (
            "I can check required documents from the uploaded college resources, but please mention "
            "whether they are for admission, examination, hostel, or another purpose."
        )
        suggestions = [
            "What documents are required for admission?",
            "What documents are needed for hostel admission?",
            "What certificates are required?",
        ]
    elif any(term in q for term in ["course", "courses", "programme", "programmes", "subject", "subjects"]):
        if any(term in q for term in ["undergraduate", "postgraduate", "certificate"]) or subject_detail:
            return None
        answer = (
            "I couldn't find specific information about that in the college documents. "
            "Could you provide more details, such as the department or course level?"
        )
        suggestions = [
            "What undergraduate courses are offered?",
            "What postgraduate courses are available?",
            "What certificate courses are available?",
        ]

    if not answer:
        return None

    return make_response(
        answer,
        suggestions=suggestions,
        response_type="clarification",
        retrieval_query=query,
    )


# TODO: split
def _legacy_expand_query(query: str) -> str:
    """Expand base queries using vocabulary dictionaries and synonym sets."""
    original_query = (query or "").strip()
    q = normalize_query_text(original_query)

    if not q:
        return original_query

    expansions: list[str] = []

    if is_person_lookup_query(original_query):
        return expand_person_lookup_query(original_query)
    if is_staff_query(original_query):
        return build_staff_retrieval_query(original_query)

    entities = extract_query_entities(original_query)
    target = entities.get("target")
    role = entities.get("role")

    if target:
        target_text = str(target).strip()
        if target_text and target_text not in expansions:
            expansions.append(target_text)

    if role:
        role_text = normalize_text(str(role))
        if role_text and role_text not in expansions:
            expansions.append(role_text)

        if "warden" in role_text or "superintendent" in role_text:
            expansions.append("hostel hall warden superintendent name designation")

        if any(term in role_text for term in ["coordinator", "chairman", "chairperson", "member", "secretary"]):
            expansions.append("committee cell members name designation")

        if "principal" in role_text:
            expansions.append("college authorities administration name designation")

        if "staff" in role_text or "teacher" in role_text or "faculty" in role_text:
            expansions.append("teaching staff faculty department head designation")

    exact_topic = extract_role_query(query).get("target") or extract_exact_topic(query)
    if exact_topic:
        expansions.append(exact_topic)

    if is_hostel_query(original_query):
        expansions.append(
            "hostel admission hostel application form submit warden parent guardian "
            "hostel prospectus boys hostel girls hostel hostel rules hostel eligibility hostel fees"
        )

    if is_procedural_query(original_query):
        expansions.append(
            "application form submit submitted office warden principal admission parent guardian "
            "documents required eligibility admission procedure application process"
        )

    for key, expanded in QUERY_EXPANSIONS.items():
        if key in q and expanded not in expansions:
            expansions.append(expanded)

    words = re.findall(r"\w+", q)
    for word in words:
        matches = get_close_matches(word, QUERY_EXPANSIONS.keys(), n=1, cutoff=0.82)
        if matches:
            expanded = QUERY_EXPANSIONS[matches[0]]
            if expanded not in expansions:
                expansions.append(expanded)

    if not expansions:
        return original_query
    return original_query + " " + " ".join(expansions)

def expand_query(query: str, intent: dict | None = None) -> list[str] | str:
    """
    Goal 7: Query Expansion using LLM to generate 3 alternative phrasings.
    If intent is None, falls back to legacy string expansion to avoid breaking existing code.
    """
    if intent is None:
        return _legacy_expand_query(query)

    from llm import generate
    system_prompt = (
        "You are an AI query expander. Given a user query and its detected intent context, "
        "generate exactly 3 alternative phrasings or keyword clusters that would help retrieve "
        "relevant documents from a vector database. Output each phrasing on a new line. Do not number them. "
        "Do not include any intro or outro text."
    )
    user_prompt = f"Query: {query}\nIntent Context: {intent}"
    
    try:
        response = generate(user_prompt=user_prompt, system_prompt=system_prompt, temperature=0.7)
        lines = [line.strip("- *0123456789.") for line in response.splitlines() if line.strip()]
        return lines[:3]
    except Exception as e:
        print(f"[QueryExpansion] LLM failed: {e}")
        return [_legacy_expand_query(query)]


def is_followup_query(query: str) -> bool:
    """Check if query is conversational followup (formatting adjustments)."""
    q = normalize_query_text(query)
    if not q:
        return False
    topic_words = [
        "committee", "cell", "department", "departments", "course", "courses",
        "programme", "programmes", "program", "programs", "fee", "fees",
        "admission", "hostel", "library", "attendance", "principal", "computer",
        "science", "website", "rules", "guidelines", "contact", "email", "phone",
        "address", "iqac", "ragging", "exam", "examination", "club", "clubs",
    ]
    if any(word in q for word in topic_words):
        return False
    if any(pattern in q for pattern in FORMAT_FOLLOWUP_PATTERNS + DETAIL_FOLLOWUP_PATTERNS):
        return True
    # Reference markers must be whole words/phrases. A raw substring check made
    # standalone topics such as "facilities" match the marker "it".
    return any(
        re.search(rf"\b{re.escape(pattern)}\b", q)
        for pattern in REFERENCE_FOLLOWUP_PATTERNS
    )


def get_last_real_user_question(history: str) -> str | None:
    """Trace history to find user's last core question."""
    if not history or not history.strip():
        return None
    user_questions: list[str] = []
    for line in history.splitlines():
        line = line.strip()
        if line.lower().startswith("user:"):
            question = line.split(":", 1)[1].strip()
            if question and not is_followup_query(question):
                user_questions.append(question)
    return user_questions[-1] if user_questions else None


# ── Contextual follow-up rewriting ───────────────────────────────────────────
# Short replies that accept/continue based on what the assistant just offered.

_AFFIRMATIVE_EXACT: frozenset[str] = frozenset({
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright",
    "please", "go ahead", "go on", "continue", "proceed",
    "both", "both please", "all", "all of them", "of course",
    "please do", "yes please", "yes sure", "yes continue",
    "yes both", "tell me both", "give me both",
    "i would", "i would like that", "i'd like that",
})

_AFFIRMATIVE_CONTAINS: tuple[str, ...] = (
    "yes please", "yes i ", "yes, i ",
    "please tell me", "please provide", "please go",
    "give me the details", "give me more details", "give me more",
    "i want to know more", "i would like to know", "i'd like to know",
)


def get_last_assistant_response(history: str) -> str | None:
    """Return the last assistant turn from conversation history."""
    if not history or not history.strip():
        return None
    last_assistant: str | None = None
    for line in history.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("assistant:"):
            content = stripped[len("assistant:"):].strip()
            if content:
                last_assistant = content
    return last_assistant


def is_contextual_affirmative(query: str) -> bool:
    """True when the reply is a short acceptance signal with no embedded topic."""
    q = normalize_query_text(query).strip()
    if not q:
        return False
    if q in _AFFIRMATIVE_EXACT:
        return True
    return any(phrase in q for phrase in _AFFIRMATIVE_CONTAINS)


def _extract_offered_topics(assistant_text: str) -> list[str]:
    """
    Heuristically extract the topics the assistant offered to discuss.
    Handles patterns such as:
      "Would you like [A] or [B]?"
      "Would you like assistance with [A] or details about [B]?"
      "feel free to ask about [X] or [Y]"
      "I can also tell you about [X]"
      "Do you want to know more about [X]?"
    Returns a list of topic strings (may be empty).
    """
    # Exclude the generic "You may ask:" suggestions injected by the bot.
    text = assistant_text
    lower = text.lower()
    if "you may ask:" in lower:
        text = text[: lower.index("you may ask:")]

    _FILLER = re.compile(
        r"^(assistance with|details about|information about|more about"
        r"|me to explain|to know about|about)\s+",
        re.IGNORECASE,
    )

    def _split_offer(raw: str) -> list[str]:
        """Split 'A or [filler] B' into ['A', 'B']."""
        parts = re.split(
            r"\s+or\s+(?:details about|information about|more about"
            r"|assistance with|about)?\s*",
            raw,
            flags=re.IGNORECASE,
        )
        return [_FILLER.sub("", p).strip().rstrip("?.,;") for p in parts if p.strip()]

    # Pattern 1: "Would you like …?"
    m = re.search(r"would you like\b(.+?)(?:\?|$)", text, re.IGNORECASE | re.DOTALL)
    if m:
        topics = _split_offer(m.group(1).strip())
        if topics:
            return topics

    # Pattern 2: "feel free to ask (me) (about) …"
    m = re.search(
        r"feel free to ask\b(?:(?: me)? about)?\s+(.+?)(?:\.|,|\?|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip(".,?")
        topics = [p.strip() for p in re.split(r"\s+(?:or|and)\s+", raw, flags=re.IGNORECASE) if p.strip()]
        if topics:
            return topics

    # Pattern 3: "I can (also) tell/provide/give you (more information) about …"
    m = re.search(
        r"(?:i can(?: also)? (?:tell|provide|give) you(?:(?: more)? information)? about"
        r"|you can also ask about)\s+(.+?)(?:\.|,|\?|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip(".,?")
        topics = [p.strip() for p in re.split(r"\s+(?:or|and)\s+", raw, flags=re.IGNORECASE) if p.strip()]
        if topics:
            return topics

    # Pattern 4: "Do you want to know (more) about …?"
    m = re.search(
        r"do you want(?: to know)?(?: more)? about\s+(.+?)(?:\?|$|\.)",
        text,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip(".,?")
        if raw:
            return [raw]

    # Pattern 5: "(further/more/additional) information about X (or Y)"
    # Catches "If you need further information about Mr. Bhardwaj or his role…"
    # Terminates at comma or "?" only — NOT at period — because re.IGNORECASE
    # makes [a-z] match uppercase, causing "Mr. B" to falsely end the capture.
    # In practice the topic clause is always comma-separated from "feel free to ask".
    m = re.search(
        r"(?:further|more|additional)?\s*information about\s+(.+?)(?:,|\?|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip(".,?")
        topics = [p.strip() for p in re.split(r"\s+(?:or|and)\s+", raw, flags=re.IGNORECASE) if p.strip()]
        if topics:
            return topics

    return []


def rewrite_contextual_followup(query: str, history: str) -> tuple[str, bool]:
    """
    Convert a contextual follow-up reply into a standalone retrieval query.

    Triggered when the user says something like "yes", "okay", "tell me more",
    "give me the details" after the assistant offered specific topics.

    Returns (rewritten_query, was_rewritten).  The rewritten query is used for
    retrieval and answer generation; the original query is preserved in history.
    """
    q = normalize_query_text(query).strip()
    if not q:
        return query, False

    is_affirmative = is_contextual_affirmative(q)
    # Detail phrases are only treated as contextual when they are short (≤ 5 words)
    # and contain no embedded topic; longer detail phrases are self-sufficient.
    is_short_detail = (
        len(q.split()) <= 5
        and any(p in q for p in DETAIL_FOLLOWUP_PATTERNS)
    )

    if not (is_affirmative or is_short_detail):
        return query, False

    last_assistant = get_last_assistant_response(history)
    last_user_q = get_last_real_user_question(history)

    if not last_assistant and not last_user_q:
        return query, False

    # Try to extract what the assistant specifically offered.
    topics: list[str] = _extract_offered_topics(last_assistant) if last_assistant else []

    if topics:
        topic_str = " and ".join(topics)
        rewritten = f"Provide information about {topic_str}"
        if last_user_q:
            ctx = re.sub(
                r"^(who is|what is|tell me about|what are|how do i|can you tell me)\s+",
                "",
                last_user_q,
                flags=re.IGNORECASE,
            ).strip()
            if ctx:
                rewritten += f" in the context of {ctx}"
        return rewritten, True

    # No explicit offer found — ask for more on the previous topic.
    if last_user_q:
        return f"Provide more detailed information about {last_user_q}", True

    return query, False


def rewrite_query_with_history(query: str, history: str) -> str:
    """
    Use LLM to rewrite a query to incorporate context from conversation history.
    If the query is already standalone, returns it unmodified.
    """
    from llm import generate

    system_prompt = (
        "You are an AI query rewriter for a college Q&A system.\n"
        "Your task is to rewrite the user's latest follow-up query to be a standalone, search-friendly query "
        "by resolving any coreferences (like 'it', 'they', 'the department', 'the course', 'his', 'her', 'fees', 'rules', 'warden') "
        "using the conversation history.\n\n"
        "Rules:\n"
        "1. If the query is already standalone and does not depend on the history, output the original query exactly.\n"
        "2. If the query depends on history, rewrite it to be a complete search query (e.g., 'who is the head of department' -> 'who is the head of the Commerce department').\n"
        "3. Output ONLY the final query text. No preamble, no explanation, no quotes, no conversational filler."
    )

    user_prompt = f"Conversation History:\n{history}\n\nLatest Query: {query}\n\nStandalone Query:"

    try:
        response = generate(user_prompt=user_prompt, system_prompt=system_prompt, temperature=0.0)
        rewritten = response.strip().strip('"\'')
        return rewritten
    except Exception as e:
        print(f"[QueryExpansion] Error in rewrite_query_with_history: {e}")
        return query


def build_smart_query(query: str, history: str) -> tuple[str, str, bool]:
    """Combine followup modifiers with previous question."""
    query = (query or "").strip()

    # Contextual follow-up rewriting runs first so affirmative replies ("yes",
    # "okay", "tell me more") resolve to what the assistant offered rather than
    # just repeating the previous user question unchanged.
    rewritten, was_rewritten = rewrite_contextual_followup(query, history)
    if was_rewritten:
        return rewritten, query, True

    # Use LLM-based coreference resolution and context merging if history is present.
    if history and history.strip():
        try:
            rewritten_llm = rewrite_query_with_history(query, history)
            if rewritten_llm and rewritten_llm.strip().lower() != query.lower():
                return rewritten_llm, query, True
        except Exception as e:
            print(f"[QueryExpansion] LLM query rewrite failed: {e}")

    if is_followup_query(query):
        previous_question = get_last_real_user_question(history)
        if previous_question:
            return previous_question, query, True
    return query, query, False


def get_casual_response(query: str) -> str | None:
    """Return static answers for hi/thanks queries."""
    q = normalize_query_text(query)
    if not q:
        return None
    if q in CASUAL_RESPONSES:
        return CASUAL_RESPONSES[q]
    matches = get_close_matches(q, CASUAL_RESPONSES.keys(), n=1, cutoff=0.78)
    return CASUAL_RESPONSES[matches[0]] if matches else None


def build_generic_retrieval_query(original_query: str) -> str:
    """Category-specific lexical expansion."""
    from .intent import build_generic_retrieval_query as core_builder
    return core_builder(original_query)


def build_role_retrieval_query(query: str) -> str:
    """Role-specific lexical expansion."""
    from .intent import build_role_retrieval_query as core_builder
    return core_builder(query)


def build_staff_retrieval_query(query: str) -> str:
    """Staff-specific lexical expansion."""
    from .intent import build_staff_retrieval_query as core_builder
    return core_builder(query)


def expand_person_lookup_query(query: str) -> str:
    """Lookup-specific lexical expansion."""
    from .intent import expand_person_lookup_query as core_builder
    return core_builder(query)
