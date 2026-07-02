"""Public compatibility surface for the EduBot RAG package."""

from .filters import build_filter
from .intent import extract_personal_eligibility_case, extract_target_course_from_query
from .main import ask
from .query_expansion import (
    build_smart_eligibility_retrieval_query,
    build_smart_retrieval_query,
)
from .retrieval import keyword_retrieve_chunks, vector_retrieve_chunks
from .text_utils import normalize_query

__all__ = [
    "ask",
    "build_filter",
    "build_smart_eligibility_retrieval_query",
    "build_smart_retrieval_query",
    "extract_personal_eligibility_case",
    "extract_target_course_from_query",
    "keyword_retrieve_chunks",
    "normalize_query",
    "vector_retrieve_chunks",
]
