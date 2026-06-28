"""
db.py - ChromaDB setup for EduBot

Purpose:
- One stable ChromaDB collection for all EduBot chunks
- Persistent local storage
- Cosine distance for normalized SentenceTransformer embeddings
- Clean metadata defaults
- Stable chunk IDs
- Soft delete / restore / hard delete
- Debug helpers for retrieval problems
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


# =============================================================================
# CONFIG
# =============================================================================

COLLECTION_NAME = "edubot_docs"

# Old collection names from earlier versions of the project.
# If these have data, re-ingest or migrate.
LEGACY_COLLECTION_NAMES = ("text_file",)

# Store ChromaDB inside the backend folder beside this db.py file.
# This prevents confusion from running uvicorn from different folders.
CHROMA_PATH = Path(__file__).resolve().parent / "chroma_db"


# =============================================================================
# CLIENT + COLLECTION
# =============================================================================

client = chromadb.PersistentClient(
    path=str(CHROMA_PATH),
    settings=Settings(
        anonymized_telemetry=False,
    ),
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={
        "hnsw:space": "cosine",
    },
)


# Warn if old collections have data.
for legacy_name in LEGACY_COLLECTION_NAMES:
    try:
        legacy_collection = client.get_collection(legacy_name)
        legacy_count = legacy_collection.count()
    except Exception:
        continue

    if legacy_count:
        print(
            "[EduBot DB WARNING] Found legacy ChromaDB collection "
            f"'{legacy_name}' with {legacy_count} chunks. Active collection is "
            f"'{COLLECTION_NAME}'. Re-ingest documents into '{COLLECTION_NAME}' "
            "or migrate old chunks before relying on retrieval."
        )


# =============================================================================
# METADATA HELPERS
# =============================================================================

def normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """
    Chroma metadata values should be simple types:
    str, int, float, bool.

    This function also guarantees consistent metadata fields for filtering.
    """

    metadata = dict(metadata or {})

    defaults: dict[str, Any] = {
        "filename": "unknown",
        "source_filename": "unknown",

        # PDF / document location
        "page": 0,
        "page_label": "",
        "page_range": "",
        "total_pages": 0,
        "chunk_index": 0,

        # Content organization
        "section_title": "general",
        "document_type": "general",
        "department": "general",
        "year": "general",
        "file_type": "unknown",
        "heading": "",
        "section": "",
        "category": "general",
        "doc_type": "unknown",

        # Knowledge hierarchy / authority (see rag/authority.py). Defaults are the
        # "standard" (non-Tier-1) values; Tier 1 docs are stamped at ingest time
        # and via scripts/backfill_authority_metadata.py.
        "priority_level": "standard",
        "authority_score": 50,
        "hostel_type": "none",
        "display_name": "",
        "version": "general",
        "programme": "general",
        "section_heading": "",
        "page_number": 0,

        # Source info
        "source_type": "upload",       # upload, website, website_pdf, website_links
        "source_url": "",
        "source_pdf_filename": "",
        "crawl_base_url": "",

        # RAG / Crawl info
        "url": "",
        "title": "",
        "domain": "",
        "crawl_timestamp": "",
        "crawl_method": "",
        "document_year": "",
        "document_date": "",

        # Access / status
        "scope": "official",          # official, personal
        "uploaded_by": "admin",
        "user_id": "admin",
        "session_id": "admin",
        "deleted": False,
        "status": "active",

        # Debug / quality
        "text_hash": "",
        "word_count": 0,
        "char_count": 0,
        "is_toc": False,
        "ocr_used": False,
        "tables_extracted": False,
    }

    for key, value in defaults.items():
        metadata.setdefault(key, value)

    normalized: dict[str, Any] = {}

    for key, value in metadata.items():
        if value is None:
            value = defaults.get(key, "")

        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = str(value)

    return normalized


def is_deleted_metadata_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value == 1

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "deleted",
        }

    return False


def is_active_metadata_value(value: Any) -> bool:
    if value is None:
        return True

    return str(value).strip().lower() not in {
        "deleted",
        "inactive",
        "archived",
    }


def metadata_is_active(meta: dict[str, Any] | None) -> bool:
    meta = meta or {}

    if is_deleted_metadata_value(meta.get("deleted")):
        return False

    if not is_active_metadata_value(meta.get("status")):
        return False

    return True


def metadata_allows_official_query(meta: dict[str, Any] | None) -> bool:
    """
    Use this if you want a DB-level official-doc filter.

    rag.py can also keep its own version, but this helper is useful for debugging.
    """

    meta = meta or {}

    if not metadata_is_active(meta):
        return False

    scope = str(meta.get("scope") or "").strip().lower()

    # Empty scope is allowed for older chunks.
    return scope in {"", "official", "admin"}


# =============================================================================
# ID HELPERS
# =============================================================================

def _safe_id_text(value: Any) -> str:
    value = str(value or "unknown").replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_\-.]", "_", value)


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:24]


def stable_chunk_id(
    filename: str,
    page: Any,
    chunk_index: int,
    hash_value: str,
) -> str:
    safe_filename = _safe_id_text(filename)
    safe_page = _safe_id_text(page)
    safe_hash = _safe_id_text(hash_value or "nohash")

    return f"{safe_filename}_p{safe_page}_c{chunk_index}_{safe_hash}"


# =============================================================================
# WRITE FUNCTIONS
# =============================================================================

def add_chunks(
    chunks: list[str],
    filename: str,
    embeddings: list[list[float]],
    pages: list[int] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    metadatas: list[dict[str, Any]] | None = None,
    ids: list[str] | None = None,
) -> int:
    """
    Add or update chunks in ChromaDB.

    Use this from ingestion.py after:
    1. text extraction
    2. cleaning
    3. chunking
    4. embedding
    """

    if not chunks:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length.")

    if pages is None:
        pages = [0] * len(chunks)

    if metadatas is None:
        metadatas = [
            {
                "filename": filename,
                "source_filename": filename,
                "page": pages[i] if i < len(pages) else 0,
                "chunk_index": i,
                **(extra_metadata or {}),
            }
            for i in range(len(chunks))
        ]
    elif len(metadatas) != len(chunks):
        raise ValueError("chunks and metadatas must have the same length.")

    final_metadatas: list[dict[str, Any]] = []

    for i, metadata in enumerate(metadatas):
        metadata = dict(metadata or {})

        metadata.setdefault("filename", filename)
        metadata.setdefault("source_filename", filename)
        metadata.setdefault("page", pages[i] if i < len(pages) else 0)
        metadata.setdefault("chunk_index", i)

        metadata.setdefault("word_count", len(str(chunks[i]).split()))
        metadata.setdefault("char_count", len(str(chunks[i])))
        metadata.setdefault("text_hash", text_hash(chunks[i]))
        # §5: chunk_id is SHA-256 of chunk text (full hash for spec compliance)
        metadata.setdefault("chunk_id", hashlib.sha256(str(chunks[i]).encode("utf-8")).hexdigest())

        final_metadatas.append(normalize_metadata(metadata))

    if ids is None:
        ids = [
            stable_chunk_id(
                filename=str(final_metadatas[i].get("filename", filename)),
                page=final_metadatas[i].get("page", 0),
                chunk_index=int(final_metadatas[i].get("chunk_index", i)),
                hash_value=str(final_metadatas[i].get("text_hash", "")),
            )
            for i in range(len(chunks))
        ]
    elif len(ids) != len(chunks):
        raise ValueError("chunks and ids must have the same length.")

    # One-line explanation: Get Chroma's max batch size dynamically if possible, otherwise default to a safe constant (4000) to prevent ValueError.
    max_batch_size = 4000
    if hasattr(collection, "_client") and hasattr(collection._client, "get_max_batch_size"):
        try:
            max_batch_size = collection._client.get_max_batch_size()
        except Exception:
            pass
    if max_batch_size is None or max_batch_size <= 0:
        max_batch_size = 4000

    # One-line explanation: Batch insertions/upserts to prevent crashing when exceeding ChromaDB max batch size.
    total_chunks = len(chunks)
    for start_idx in range(0, total_chunks, max_batch_size):
        end_idx = start_idx + max_batch_size
        batch_chunks = chunks[start_idx:end_idx]
        batch_embeddings = embeddings[start_idx:end_idx]
        batch_metadatas = final_metadatas[start_idx:end_idx]
        batch_ids = ids[start_idx:end_idx]

        print(f"[ChromaDB] Upserting batch {start_idx // max_batch_size + 1}: chunks {start_idx} to {min(end_idx, total_chunks)} of {total_chunks}...")
        collection.upsert(
            documents=batch_chunks,
            embeddings=batch_embeddings,
            metadatas=batch_metadatas,
            ids=batch_ids,
        )

    return len(chunks)


# =============================================================================
# DELETE / RESTORE
# =============================================================================

def soft_delete_document(filename: str) -> int:
    """
    Mark a document as deleted without removing vectors from ChromaDB.
    """

    results = collection.get(
        where={"filename": {"$eq": filename}},
        include=["metadatas"],
    )

    ids = results.get("ids", [])

    if not ids:
        return 0

    old_metas = results.get("metadatas", [])
    new_metas: list[dict[str, Any]] = []

    for meta in old_metas:
        updated = dict(meta or {})
        updated["deleted"] = True
        updated["status"] = "deleted"
        new_metas.append(normalize_metadata(updated))

    collection.update(
        ids=ids,
        metadatas=new_metas,
    )

    return len(ids)


def delete_document(filename: str) -> int:
    """
    Backward-compatible delete function.
    Uses soft delete.
    """

    return soft_delete_document(filename)


def hard_delete_document(filename: str) -> int:
    """
    Permanently delete a document's chunks from ChromaDB.
    """

    results = collection.get(
        where={"filename": {"$eq": filename}},
        include=[],
    )

    ids = results.get("ids", [])

    if not ids:
        return 0

    collection.delete(ids=ids)

    return len(ids)


def restore_document(filename: str) -> int:
    """
    Restore a soft-deleted document.
    """

    results = collection.get(
        where={"filename": {"$eq": filename}},
        include=["metadatas"],
    )

    ids = results.get("ids", [])

    if not ids:
        return 0

    old_metas = results.get("metadatas", [])
    new_metas: list[dict[str, Any]] = []

    for meta in old_metas:
        updated = dict(meta or {})
        updated["deleted"] = False
        updated["status"] = "active"
        new_metas.append(normalize_metadata(updated))

    collection.update(
        ids=ids,
        metadatas=new_metas,
    )

    return len(ids)


# =============================================================================
# READ / LIST FUNCTIONS
# =============================================================================

def list_documents() -> list[str]:
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", [])

    filenames = {
        str(meta.get("filename", "unknown"))
        for meta in metadatas
        if meta
    }

    return sorted(filenames)


def list_active_documents() -> list[str]:
    results = collection.get(
        include=["metadatas"],
    )

    metadatas = results.get("metadatas", [])

    filenames = {
        str(meta.get("filename", "unknown"))
        for meta in metadatas
        if meta and metadata_is_active(meta)
    }

    return sorted(filenames)


def get_document_chunks(filename: str, include_deleted: bool = False) -> dict[str, Any]:
    results = collection.get(
        where={"filename": {"$eq": filename}},
        include=["documents", "metadatas"],
    )

    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])

    items = []

    for chunk_id, doc, meta in zip(ids, docs, metas):
        meta = meta or {}

        if not include_deleted and not metadata_is_active(meta):
            continue

        items.append({
            "id": chunk_id,
            "text": doc,
            "metadata": meta,
        })

    items.sort(
        key=lambda item: (
            str(item["metadata"].get("filename", "")),
            int(item["metadata"].get("page", 0) or 0),
            int(item["metadata"].get("chunk_index", 0) or 0),
        )
    )

    return {
        "filename": filename,
        "chunks": items,
        "count": len(items),
    }


# =============================================================================
# STATS / DEBUG HELPERS
# =============================================================================

def collection_stats() -> dict[str, Any]:
    all_results = collection.get(include=["metadatas"])
    all_metas = all_results.get("metadatas", [])

    total = len(all_metas)

    deleted = sum(
        1 for meta in all_metas
        if meta and is_deleted_metadata_value(meta.get("deleted"))
    )

    active = sum(
        1 for meta in all_metas
        if meta and metadata_is_active(meta)
    )

    files = sorted({
        str(meta.get("filename", "unknown"))
        for meta in all_metas
        if meta
    })

    scopes: dict[str, int] = {}
    statuses: dict[str, int] = {}
    file_types: dict[str, int] = {}
    source_types: dict[str, int] = {}

    for meta in all_metas:
        if not meta:
            continue

        scope = str(meta.get("scope", "missing"))
        status = str(meta.get("status", "missing"))
        file_type = str(meta.get("file_type", "missing"))
        source_type = str(meta.get("source_type", "missing"))

        scopes[scope] = scopes.get(scope, 0) + 1
        statuses[status] = statuses.get(status, 0) + 1
        file_types[file_type] = file_types.get(file_type, 0) + 1
        source_types[source_type] = source_types.get(source_type, 0) + 1

    return {
        "collection_name": COLLECTION_NAME,
        "chroma_path": str(CHROMA_PATH),
        "total_chunks": total,
        "active_chunks": active,
        "deleted_chunks": deleted,
        "unique_files": len(files),
        "files": files,
        "scopes": scopes,
        "statuses": statuses,
        "file_types": file_types,
        "source_types": source_types,
    }


def debug_find_text_terms(
    terms: list[str],
    limit: int = 20,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Debug helper to check whether expected words exist in ChromaDB.

    Example:
    debug_find_text_terms(["hostel", "warden", "hosteller"])
    """

    results = collection.get(
        include=["documents", "metadatas"],
        limit=10000,
    )

    docs = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    matches: list[dict[str, Any]] = []

    normalized_terms = [
        str(term).lower().strip()
        for term in terms
        if str(term).strip()
    ]

    for doc, meta in zip(docs, metadatas):
        meta = meta or {}

        if active_only and not metadata_is_active(meta):
            continue

        text = str(doc or "")
        text_lower = text.lower()

        if any(term in text_lower for term in normalized_terms):
            matches.append({
                "metadata": meta,
                "preview": text[:1000],
            })

        if len(matches) >= limit:
            break

    return matches


def debug_filename_summary(limit: int = 20000) -> dict[str, Any]:
    """
    Shows chunk counts per filename.
    Useful after ingestion.
    """

    results = collection.get(
        include=["metadatas"],
        limit=limit,
    )

    metadatas = results.get("metadatas", [])

    counts: dict[str, int] = {}

    for meta in metadatas:
        if not meta or not metadata_is_active(meta):
            continue

        filename = str(meta.get("filename", "unknown"))
        counts[filename] = counts.get(filename, 0) + 1

    return {
        "total_active_files": len(counts),
        "files": dict(sorted(counts.items(), key=lambda item: item[0].lower())),
    }


def reset_collection(confirm: bool = False) -> bool:
    """
    Danger: deletes the active collection.

    Use only during development when you want to re-ingest everything.
    """

    if not confirm:
        print("[EduBot DB] reset_collection skipped. Pass confirm=True to delete.")
        return False

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    global collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
        },
    )

    print(f"[EduBot DB] Reset collection: {COLLECTION_NAME}")
    return True
