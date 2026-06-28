from __future__ import annotations
import re

from .config import WEBSITE_FILE_TYPES
from .text_utils import (
    is_active_metadata_value,
    is_deleted_metadata_value,
    normalize_text,
)


def is_toc_candidate(document: str, meta: dict | None = None) -> bool:
    """Assess if a document chunk looks like it is from a table of contents."""
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




def build_filter(
    use_personal_docs: bool,
    user_id: str | None,
    department: str | None,
    year: str | None,
    document_type: str | None,
) -> dict | None:
    """
    Build a standard ChromaDB metadata filter query based on user scope,
    department, year, and document type constraints.
    """
    base_filters: list[dict] = []

    if use_personal_docs and user_id:
        base_filters.extend([
            {"deleted": {"$eq": False}},
            {"scope": {"$eq": "personal"}},
            {"user_id": {"$eq": user_id}},
        ])
        return {"$and": base_filters}

    if not any([
        department and department != "general",
        year and year != "general",
        document_type and document_type != "general",
    ]):
        return None

    if department and department != "general":
        base_filters.append({"department": {"$in": [department, "general"]}})
    if year and year != "general":
        base_filters.append({"year": {"$in": [str(year), "general"]}})
    if document_type and document_type != "general":
        base_filters.append({"document_type": {"$in": [document_type, "general"]}})

    if not base_filters:
        return None
    if len(base_filters) == 1:
        return base_filters[0]
    return {"$and": base_filters}


def metadata_allows_query(meta: dict | None, use_personal_docs: bool = False) -> bool:
    """
    Check if a retrieved chunk's metadata allows it to be used under the current query scope.
    Handles deletion status, active status, and scope logic.
    """
    meta = meta or {}
    if is_deleted_metadata_value(meta.get("deleted")) or not is_active_metadata_value(meta.get("status")):
        return False
    scope     = meta.get("scope")
    file_type = str(meta.get("file_type") or "")
    if use_personal_docs:
        return scope in {None, "personal"}
    if file_type in WEBSITE_FILE_TYPES:
        return scope in {None, "official"}
    return scope in {None, "official"}


def meta_text(meta: dict | None) -> str:
    """
    Concatenate relevant fields in the metadata into a single string.
    Used for lexical alignment (e.g. filename, sections, URLs).
    """
    meta = meta or {}
    return " ".join(
        str(meta.get(key, "") or "")
        for key in (
            "filename", "source_filename", "section_title",
            "document_type", "department", "year",
            "source_url",
            "source_pdf_filename",
        )
    )


def candidate_dedupe_key(document: str, meta: dict | None) -> str:
    """
    Compute a unique hash or identifier key for a chunk to prevent duplicate chunks in context.
    """
    meta = meta or {}
    text_hash = str(meta.get("text_hash") or "").strip()
    if text_hash:
        return text_hash
    source_url = str(meta.get("source_url") or "").strip()
    if source_url:
        return f"{source_url}::{meta.get('page', '?')}::{meta.get('chunk_index', '?')}"
    return (
        f"{meta.get('filename', 'unknown')}-{meta.get('page', '?')}"
        f"-{meta.get('chunk_index', '?')}-{hash((document or '')[:240])}"
    )
