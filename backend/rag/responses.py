from __future__ import annotations

"""
rag/responses.py
Canned responses and fallback response builders for St. Anthony's College EduBot.
Imports schemas.py, config.py, intent.py, suggestions.py, prompts.py, answer_builders.py, and external llm.py.
"""

import logging
from typing import Any

try:
    from llm import generate
except ImportError:
    from ..llm import generate

from .config import (
    DEBUG_RAG,
    HOMEWORK_REFUSAL_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    CLARIFICATION_MESSAGE,
    DEFAULT_SUGGESTED_QUESTIONS,
    NOT_FOUND_MESSAGE,
    PROGRAMME_NOT_FOUND_MESSAGE,
    PROGRAMME_NOT_AVAILABLE_MESSAGE,
    PROGRAMME_ADMISSION_UNVERIFIED_SUFFIX,
    PROGRAMME_FOLLOWUP_SUGGESTIONS,
)
from .intent import (
    classify_admission_query,
    extract_personal_eligibility_case,
    extract_target_course_from_query,
    extract_role_query,
    _display_department_name,
    normalize_query,
    normalize_text,
    extract_department_from_query,
    is_eligibility_query,
    PROGRAMME_DISPLAY,
    COURSE_ALIASES,
    SUBJECT_ALIASES,
)
from .prompts import LLM_SYSTEM
from .schemas import make_response
from .suggestions import get_suggested_questions
from .text_utils import postprocess_answer
from .answer_builders import append_supporting_action_details


def debug_rag(message: str, *values: Any) -> None:
    """Redirect debug statements to the logging module when DEBUG_RAG is active."""
    if DEBUG_RAG:
        logging.info(f"[DEBUG_RAG] {message} " + " ".join(map(str, values)))


def homework_refusal_response() -> dict[str, Any]:
    return make_response("I am EduBot, an AI designed to assist with college inquiries. I cannot help with homework or unrelated topics.", response_type="homework_refusal")

def personal_records_refusal_response() -> dict[str, Any]:
    return make_response("I cannot access your personal records. Please log in to the student portal.", response_type="personal_records")


def out_of_scope_response() -> dict[str, Any]:
    return make_response(OUT_OF_SCOPE_MESSAGE, response_type="out_of_scope")


def clarification_response() -> dict[str, Any]:
    return make_response(CLARIFICATION_MESSAGE, response_type="clarification")


def guided_college_response(query: str) -> dict[str, Any]:
    q = normalize_query(query)
    if "fee" in q:
        suggestions = [
            "What is the fee structure?",
            "What is the application fee?",
            "What are the laboratory charges?",
        ]
    elif "course" in q or "program" in q or "programme" in q:
        suggestions = [
            "What undergraduate courses are offered?",
            "What postgraduate courses are available?",
            "What certificate courses are available?",
        ]
    elif "club" in q:
        suggestions = [
            "What clubs are available in the college?",
            "What cells are available?",
            "What committees are there in the college?",
        ]
    elif "hostel" in q:
        suggestions = [
            "What are the hostel rules?",
            "Who is eligible for hostel admission?",
            "What documents are needed for hostel admission?",
        ]
    elif "document" in q or "admission" in q:
        suggestions = [
            "What documents are required for admission?",
            "What is the admission process?",
            "What are the eligibility criteria for admission?",
        ]
    else:
        suggestions = DEFAULT_SUGGESTED_QUESTIONS
    answer = (
        "I can help with that. Please choose a more specific question so I can answer "
        "accurately from the uploaded college resources."
    )
    return make_response(answer, suggestions=suggestions, response_type="guided", retrieval_query=query)


# TODO: split
def smart_not_found_answer(query: str, exact_case_not_confirmed: bool = False) -> str:
    q = normalize_query(query)
    admission_info = classify_admission_query(query)
    category = str(admission_info.get("category") or "")
    eligibility_case = extract_personal_eligibility_case(query)
    dept = extract_department_from_query(query)
    target_course = (
        admission_info.get("target_course")
        or eligibility_case.get("target_course")
        or extract_target_course_from_query(query)
    )
    if not target_course and dept:
        dept_lower = dept.lower()
        target_course = COURSE_ALIASES.get(dept_lower) or SUBJECT_ALIASES.get(dept_lower) or dept.title()

    if exact_case_not_confirmed:
        return (
            "The available college resources mention related admission information, "
            "but they don't clearly confirm your exact situation. "
            "Please check the official admission notice or contact the admission office directly."
        )

    if eligibility_case["is_personal_eligibility"] or any(
        term in q for term in ["admission", "apply", "eligible", "eligibility", "join", "take admission"]
    ):
        target = target_course or eligibility_case.get("subject")
        if target:
            return (
                f"I couldn't find specific admission or eligibility details for **{target}** "
                "in the available college documents. "
                "You may want to check the official prospectus or contact the admission office directly."
            )
        return (
            "I can look up admission and eligibility details from the college documents, "
            "but I need a bit more information — could you mention the course or programme "
            "you're interested in?"
        )

    if category == "admission_dates":
        return (
            "I couldn't find a specific admission date or deadline in the uploaded college resources. "
            "Please check the official admission notice or the college website."
        )

    if category == "admission_process":
        return (
            "I couldn't find a clear description of the admission process in the uploaded documents. "
            "The college prospectus or official website would have this information."
        )

    if category == "admission_form":
        return (
            "I couldn't find details about the admission form or application mode "
            "in the uploaded college resources. Please check the official college website."
        )

    if category == "merit_selection":
        return (
            "I couldn't find clear merit list or selection criteria in the uploaded resources. "
            "Please check the official admission notice for this information."
        )

    if category == "documents":
        return (
            "I couldn't find a clear required-documents list for this question "
            "in the uploaded college resources. The college prospectus usually has this."
        )

    if category == "courses":
        return (
            "I couldn't find a clear course or programme list for this question "
            "in the uploaded college resources."
        )

    if category == "contact":
        return (
            "I couldn't find specific contact information for this in the uploaded resources. "
            "Please check the college website or visit the office directly."
        )

    if category == "role_person" or extract_role_query(query).get("role"):
        return (
            "I couldn't find that person's name clearly in the available college resources. "
            "The information may be in a document that hasn't been uploaded yet."
        )

    if any(term in q for term in ["hostel", "accommodation", "warden", "hall"]):
        return (
            "I couldn't find clear hostel information for this question in the uploaded resources. "
            "Please check whether the hostel prospectus or hostel rules document has been uploaded, "
            "or contact the hostel office directly."
        )

    if any(term in q for term in ["fee", "fees", "pay", "payment", "amount", "charges"]):
        if target_course:
            return (
                f"I couldn't find specific fee details for **{target_course}** in the uploaded resources. "
                "Please check the official prospectus or contact the college office directly."
            )
        return (
            "I couldn't find the specific fee details you're looking for in the uploaded resources. "
            "Could you mention the course, semester, or fee type? "
            "That would help me find the right section."
        )

    return NOT_FOUND_MESSAGE


def not_found_response(
    query: str = "",
    where_filter: dict | None = None,
    used_history: bool = False,
    exact_case_not_confirmed: bool = False,
    original_query: str | None = None,
    context_hint: str | None = None,
) -> dict[str, Any]:
    suggestions = get_suggested_questions(query, where_filter, context_hint=context_hint) if query else DEFAULT_SUGGESTED_QUESTIONS
    answer_query = original_query or query
    answer = smart_not_found_answer(answer_query, exact_case_not_confirmed=exact_case_not_confirmed) if answer_query else NOT_FOUND_MESSAGE
    answer = append_supporting_action_details(answer, answer_query, where_filter)
    debug_rag("not_found detected course", extract_target_course_from_query(answer_query) if answer_query else None)
    return make_response(
        answer,
        suggestions=suggestions,
        response_type="not_found",
        retrieval_query=query,
        used_history=used_history,
    )


def partial_answer_response(query: str, context: str, sources: list) -> dict:
    """
    Called when context exists but confidence is low.
    Sends to LLM with explicit 'partial info' framing.
    """
    prompt = (
        f"Context (may be incomplete):\n{context}\n\n"
        f"Question: {query}\n\n"
        "The context may only partially answer this question. "
        "Share whatever relevant information you found, and clearly note "
        "if something specific is not available. Be honest and helpful."
    )
    answer = generate(prompt, system_prompt=LLM_SYSTEM, temperature=0.1)
    return make_response(
        postprocess_answer(answer),
        sources=sources,
        retrieval_query=query,
        response_type="partial",
    )


def _staff_query_suggestions(department: str | None = None) -> list[str]:
    display = _display_department_name(department)
    if display:
        return [
            f"Who is the HOD of {display}?",
            f"Show the {display} department details",
            f"What courses are offered in {display}?",
        ]
    return [
        "What departments are available?",
        "Who is the HOD of a department?",
        "Show department details",
    ]


def programme_not_found_response(
    programme: str,
    query: str = "",
    where_filter: dict | None = None,
    availability: bool = False,
    used_history: bool = False,
    retrieval_query: str = "",
) -> dict[str, Any]:
    """
    Grounded, confidence-aware response for a programme that is NOT present in the
    retrieved college resources. Prevents the LLM from hallucinating admission
    information for programmes the college does not offer.

    `programme` is the canonical code (e.g. 'BCA'); `availability` selects between
    "is it offered?" phrasing and "I couldn't find it" phrasing.
    """
    display = PROGRAMME_DISPLAY.get(programme, programme)
    q = normalize_text(query)
    asks_admission = is_eligibility_query(query) or any(
        term in q for term in ["admission", "admit", "apply", "application", "join", "fee", "fees", "seat"]
    )

    if availability and not asks_admission:
        answer = PROGRAMME_NOT_AVAILABLE_MESSAGE.format(programme=display)
    else:
        answer = PROGRAMME_NOT_FOUND_MESSAGE.format(programme=display)
        if asks_admission:
            answer += PROGRAMME_ADMISSION_UNVERIFIED_SUFFIX

    # Inline follow-ups (§ better UX). Kept in the answer text because suggested
    # questions may be disabled in config; the structured field is still populated.
    bullets = "\n".join(f"• {s}" for s in PROGRAMME_FOLLOWUP_SUGGESTIONS)
    answer = f"{answer}\n\nYou may ask:\n{bullets}"

    return make_response(
        answer,
        sources=[],
        suggestions=list(PROGRAMME_FOLLOWUP_SUGGESTIONS),
        response_type="programme_not_found",
        retrieval_query=retrieval_query or query,
        used_history=used_history,
    )


def staff_not_found_response(department: str | None = None) -> dict[str, Any]:
    department_display = _display_department_name(department)
    if department_display:
        answer = (
            f"I couldn't find a clear teaching-staff list for {department_display} "
            "in the available college resources. If the documents mention only the HOD/Head, "
            "I can provide that, but the full teaching-staff list is not clearly available."
        )
    else:
        answer = (
            "I couldn't find a clear teaching-staff list in the available college resources. "
            "Please specify the department."
        )
    return make_response(
        answer,
        sources=[],
        suggestions=_staff_query_suggestions(department),
        response_type="staff_not_found",
    )
