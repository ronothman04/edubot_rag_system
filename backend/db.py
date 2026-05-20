# import chromadb

# client = chromadb.PersistentClient(path="./chroma_db")

# collection = client.get_or_create_collection(
#     name="text_file"
# )


"""
db.py  ─  ChromaDB setup for EduBot

Key changes from v1:
  • hnsw:space = "cosine"   — REQUIRED for distance-threshold filtering in rag.py
  • add_chunks()            — ingest pre-chunked text with proper metadata
  • delete_document()       — soft-delete (sets deleted=True) by filename
  • hard_delete_document()  — permanently removes all chunks for a filename
  • restore_document()      — reverses a soft-delete
  • list_documents()        — all filenames including deleted
  • list_active_documents() — filenames that are NOT deleted
  • collection_stats()      — quick debug / health-check helper
"""

from __future__ import annotations

import uuid
from typing import Any

import chromadb
from chromadb.config import Settings

# ── Client ───────────────────────────────────────────────────────────────────

client = chromadb.PersistentClient(
    path="./chroma_db",
    settings=Settings(anonymized_telemetry=False),
)

# ── Collection ───────────────────────────────────────────────────────────────
# CRITICAL: hnsw:space must be "cosine" so that the distances returned by
# collection.query() are cosine distances (0 = identical, 2 = opposite).
# rag.py uses DISTANCE_THRESHOLD = 0.75 which assumes cosine space.
#
# WARNING: You CANNOT change hnsw:space on an existing collection.
# If you had an old "text_file" collection, delete it first:
#   client.delete_collection("text_file")
# and re-ingest your documents into the new collection below.

collection = client.get_or_create_collection(
    name="edubot_docs",
    metadata={"hnsw:space": "cosine"},
)


# ── Ingestion helper ─────────────────────────────────────────────────────────

def add_chunks(
    chunks: list[str],
    filename: str,
    embeddings: list[list[float]],
    pages: list[int] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> int:
    """
    Add a list of text chunks from a single document into ChromaDB.

    Parameters
    ----------
    chunks      : List of text strings (one per chunk).
    filename    : Source filename, e.g. "biology_notes.pdf".
    embeddings  : Pre-computed embeddings (one per chunk).
                  Generate with: bi_encoder.encode(chunks).tolist()
    pages       : Optional page numbers aligned with chunks.
                  Defaults to 0 for all chunks if not provided.
    extra_metadata : Any additional key-value pairs to store per chunk.

    Returns
    -------
    Number of chunks successfully added.

    Example usage
    -------------
    from sentence_transformers import SentenceTransformer
    from db import add_chunks

    encoder = SentenceTransformer("all-MiniLM-L6-v2")
    chunks  = ["Photosynthesis is...", "Chlorophyll absorbs..."]
    embeds  = encoder.encode(chunks).tolist()
    add_chunks(chunks, "biology.pdf", embeds, pages=[1, 1])
    """
    if not chunks:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length.")

    if pages is None:
        pages = [0] * len(chunks)

    metadatas = [
        {
            "filename": filename,
            "page": pages[i] if i < len(pages) else 0,
            "deleted": False,
            **(extra_metadata or {}),
        }
        for i in range(len(chunks))
    ]

    ids = [str(uuid.uuid4()) for _ in chunks]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    return len(chunks)


# ── Soft delete ───────────────────────────────────────────────────────────────

def delete_document(filename: str) -> int:
    """
    Soft-delete all chunks belonging to a filename.
    Sets deleted=True — chunks stay in the DB but are excluded
    from all queries via rag.py's where={"deleted": False} filter.

    Returns the number of chunks soft-deleted.
    """
    results = collection.get(
        where={"filename": filename},
        include=["metadatas"],
    )
    ids = results.get("ids", [])
    if not ids:
        return 0

    collection.update(
        ids=ids,
        metadatas=[{"deleted": True} for _ in ids],
    )
    return len(ids)


# ── Hard delete ───────────────────────────────────────────────────────────────

def hard_delete_document(filename: str) -> int:
    """
    Permanently remove all chunks for a filename from ChromaDB.
    Cannot be undone — use delete_document() for reversible removal.

    Returns the number of chunks deleted.
    """
    results = collection.get(
        where={"filename": filename},
        include=[],
    )
    ids = results.get("ids", [])
    if not ids:
        return 0

    collection.delete(ids=ids)
    return len(ids)


# ── Restore ───────────────────────────────────────────────────────────────────

def restore_document(filename: str) -> int:
    """
    Reverse a soft-delete by setting deleted=False for all chunks
    belonging to the given filename.

    Returns the number of chunks restored.
    """
    results = collection.get(
        where={"filename": filename},
        include=["metadatas"],
    )
    ids = results.get("ids", [])
    if not ids:
        return 0

    collection.update(
        ids=ids,
        metadatas=[{"deleted": False} for _ in ids],
    )
    return len(ids)


# ── Listing helpers ───────────────────────────────────────────────────────────

def list_documents() -> list[str]:
    """Return sorted unique filenames in the collection (including deleted)."""
    results   = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", [])
    filenames = {m.get("filename", "unknown") for m in metadatas if m}
    return sorted(filenames)


def list_active_documents() -> list[str]:
    """Return sorted unique filenames that have NOT been soft-deleted."""
    results   = collection.get(where={"deleted": False}, include=["metadatas"])
    metadatas = results.get("metadatas", [])
    filenames = {m.get("filename", "unknown") for m in metadatas if m}
    return sorted(filenames)


# ── Debug / health-check ──────────────────────────────────────────────────────

def collection_stats() -> dict[str, Any]:
    """
    Return basic statistics about the collection for debugging.

    Example output:
    {
        "total_chunks":   312,
        "active_chunks":  298,
        "deleted_chunks": 14,
        "unique_files":   5,
        "files": ["bio.pdf", "chem.pdf", ...]
    }
    """
    all_results = collection.get(include=["metadatas"])
    all_metas   = all_results.get("metadatas", [])

    total    = len(all_metas)
    deleted  = sum(1 for m in all_metas if m and m.get("deleted") is True)
    active   = total - deleted
    files    = sorted({m.get("filename", "unknown") for m in all_metas if m})

    return {
        "total_chunks":   total,
        "active_chunks":  active,
        "deleted_chunks": deleted,
        "unique_files":   len(files),
        "files":          files,
    }