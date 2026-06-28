from __future__ import annotations

"""
rag/suggestions.py
Default suggested questions and suggestion helpers for EduBot RAG.
Imports config.py only.
"""

from .config import DEFAULT_SUGGESTED_QUESTIONS


def get_suggested_questions(
    query: str,
    where_filter: dict | None = None,
    context_hint: str | None = None
) -> list[str]:
    """
    Deterministic suggestion function. No LLM calls.
    Returns 3 relevant follow-up questions based on query intent keywords.
    """
    if context_hint:
        hint = str(context_hint or "").lower().strip()
        if "fee" in hint or "₹" in hint:
            return [
                "What is the application fee?",
                "What is the semester fee structure?",
                "What are the laboratory charges?"
            ]
        if "department of" in hint and "head" in hint:
            return [
                "What departments are available?",
                "Who is the HOD of Computer Science?",
                "What courses are offered?"
            ]
        if "hostel" in hint or "warden" in hint:
            return [
                "What are the hostel rules?",
                "Who is the hostel warden?",
                "What documents are needed for hostel admission?"
            ]
        if any(t in hint for t in ["ncc", "nss", "club", "association", "cultural", "activity"]):
            return [
                "What clubs are available?",
                "What co-curricular activities are available?",
                "What are the NCC and NSS activities?"
            ]
        if any(t in hint for t in ["committee", "cell", "members", "coordinator"]):
            return [
                "Who are the members of the Website Committee?",
                "What committees are there?",
                "Who is the IQAC coordinator?"
            ]

    q = str(query or "").lower().strip()

    # Attendance
    if "attendance" in q:
        return [
            "What is the minimum attendance required?",
            "What happens if a student has a shortage of attendance?",
            "What are the leave requirements for students?",
        ]

    # Fees
    if any(w in q for w in ["fee", "fees", "payment", "application fee"]):
        return [
            "What is the application fee for admission?",
            "What is the semester fee structure?",
            "What are the laboratory charges?",
        ]

    # Departments
    if any(w in q for w in ["department", "departments"]):
        return [
            "What departments are available in the college?",
            "Who is the HOD of the Computer Science department?",
            "What undergraduate courses are offered by the college?",
        ]

    # Undergraduate courses
    if any(w in q for w in ["undergraduate", "ug", "bachelor", "ba", "bsc", "bcom", "bba", "bca"]):
        return [
            "What undergraduate degree programs are offered?",
            "What postgraduate courses are available?",
            "What certificate courses are available?",
        ]

    # Postgraduate courses
    if any(w in q for w in ["postgraduate", "pg", "master", "msc", "mca", "ma", "mcom"]):
        return [
            "What postgraduate courses are available?",
            "What are the eligibility criteria for postgraduate admission?",
            "What undergraduate courses are offered?",
        ]

    # Certificate courses
    if "certificate" in q:
        return [
            "What certificate courses are available?",
            "What undergraduate courses are offered?",
            "What postgraduate courses are available?",
        ]

    # Admission / documents / eligibility
    if any(w in q for w in ["admission", "document", "eligibility", "eligible", "apply", "application"]):
        return [
            "What documents are required for admission?",
            "What are the eligibility criteria for admission?",
            "What is the application fee?",
        ]

    # Hostel / warden
    if any(w in q for w in ["hostel", "warden", "hall", "superintendent"]):
        return [
            "What are the hostel rules?",
            "Who is the warden of Stephen Hall?",
            "What documents are needed for hostel admission?",
        ]

    # Clubs / cells / committees / activities
    if any(w in q for w in ["club", "clubs", "cell", "cells", "committee", "committees",
                             "activity", "activities", "association", "society"]):
        return [
            "What clubs are available in the college?",
            "What co-curricular activities are available?",
            "Who are the members of the Website Committee?",
        ]

    # Faculty / staff / roles
    if any(w in q for w in ["faculty", "staff", "teacher", "professor", "lecturer",
                             "hod", "head", "principal", "coordinator"]):
        return [
            "Who is the Principal of the college?",
            "Who is the HOD of the Economics department?",
            "What departments are available?",
        ]

    # Contact / website links
    if any(w in q for w in ["contact", "email", "phone", "address", "website", "link", "links"]):
        return [
            "What is the college contact information?",
            "What website links are available?",
            "What is the college address?",
        ]

    # Generic college fallback
    return DEFAULT_SUGGESTED_QUESTIONS
