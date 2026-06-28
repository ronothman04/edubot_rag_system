from __future__ import annotations
"""
rag/schemas.py
Response builders and schema helpers for St. Anthony's College EduBot.
"""

from typing import Any


from .config import DISABLE_SUGGESTED_QUESTIONS


def make_response(
    answer: str,
    sources: list[dict] | None = None,
    suggestions: list[str] | None = None,
    response_type: str = "rag",
    retrieval_query: str = "",
    used_history: bool = False,
) -> dict[str, Any]:
    """
    Format the RAG output in a standardized JSON-compatible dict structure.
    """
    sugs = [] if DISABLE_SUGGESTED_QUESTIONS else (suggestions or [])
    return {
        "answer": answer,
        "sources": sources or [],
        "suggested_questions": sugs,
        "retrieval_query": retrieval_query,
        "used_history": used_history,
        "response_type": response_type,
    }
