"""
resplit_oversized_chunks.py

Targeted (NOT full) re-embed migration for chunks already stored in ChromaDB
whose embedding text exceeds the BGE 512-token cap. SentenceTransformer
truncates silently, so the tail of each such chunk is missing from its vector
(measured ~8% of chunks). The forward fix (ingestion.split_chunks_for_embedding)
prevents this for new ingestion; this script repairs EXISTING oversized chunks
without a full re-ingestion or re-crawl.

Per oversized chunk it: splits the stored text into budget-sized pieces, re-embeds
each piece with the SAME Title/Source/Section header used at ingest, writes the
pieces as new chunks (ids derived from the parent id + a piece suffix, inheriting
the parent metadata), then deletes the original. It is additive-then-delete and
content-preserving — no text is dropped.

IMPACT (read before --apply):
  * Only chunks with >512 embedding tokens are touched; all others are untouched.
  * Net new embeddings generated (~2-3x the oversized count); CPU, a few minutes.
  * Affected chunks get new ids; sub-pieces inherit page + chunk_index of the
    parent (treated as a cluster by related-chunk expansion). char_start/char_end
    of sub-pieces are left as the parent's (used only for ingest-time expansion).
  * BM25 index is rebuilt and caches cleared at the end.
  * Reversible only by re-ingesting the affected source files; no snapshot is taken.

Usage:
    python -m scripts.resplit_oversized_chunks            # dry-run report
    python -m scripts.resplit_oversized_chunks --apply    # perform migration
"""
from __future__ import annotations

import hashlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def _embedding_text(chunk: str, meta: dict) -> str:
    """Must match ingestion.ingest_documents' embedding-text format exactly."""
    return (
        f"Title: {meta.get('title', '')}\n"
        f"Source: {meta.get('filename', '')}\n"
        f"Section: {meta.get('heading', '')}\n\n"
        f"{chunk}"
    )


def main() -> None:
    import logging

    logging.disable(logging.CRITICAL)

    from db import collection, normalize_metadata
    from embeddings import get_embedding_model, encode_texts
    from ingestion import split_chunks_for_embedding

    apply = "--apply" in sys.argv
    print(f"=== Re-split oversized chunks ({'APPLY' if apply else 'DRY-RUN'}) ===")

    model = get_embedding_model()
    tokenizer = model.tokenizer
    budget = int(getattr(model, "max_seq_length", 512) or 512)

    got = collection.get(include=["documents", "metadatas"])
    ids = got["ids"]
    docs = got["documents"]
    metas = got["metadatas"]

    oversized = 0
    new_pieces = 0
    ids_to_delete: list[str] = []
    add_docs: list[str] = []
    add_embed_texts: list[str] = []
    add_metas: list[dict] = []
    add_ids: list[str] = []

    for cid, doc, meta in zip(ids, docs, metas):
        meta = meta or {}
        n_tokens = len(tokenizer.encode(_embedding_text(doc, meta), add_special_tokens=True))
        if n_tokens <= budget:
            continue
        pieces = split_chunks_for_embedding([doc])
        # Only act when the split actually produced smaller, multiple pieces.
        if len(pieces) <= 1:
            continue
        oversized += 1
        ids_to_delete.append(cid)
        for j, piece in enumerate(pieces):
            new_pieces += 1
            piece_hash = hashlib.sha256(
                (piece + cid).encode("utf-8")
            ).hexdigest()[:24]
            new_meta = dict(meta)
            new_meta["text_hash"] = piece_hash
            new_meta["word_count"] = len(piece.split())
            new_meta["char_count"] = len(piece)
            new_meta["text_chars"] = len(piece)
            new_meta["resplit_from"] = cid
            add_docs.append(piece)
            add_embed_texts.append(_embedding_text(piece, new_meta))
            add_metas.append(normalize_metadata(new_meta))
            add_ids.append(f"{cid}_s{j}")

    print(f"oversized chunks (>{budget} tok) : {oversized}")
    print(f"replacement pieces             : {new_pieces}")
    if oversized:
        print(f"net chunk delta                : +{new_pieces - oversized}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to perform the migration.")
        return
    if not oversized:
        print("Nothing to do.")
        return

    # Snapshot the store before this hard-to-reverse migration.
    try:
        from scripts.migration_snapshot import create_snapshot
        create_snapshot("resplit_oversized_chunks")
    except Exception as exc:
        print(f"[snapshot] WARNING: {exc}")

    # Add-then-delete so content is never absent mid-migration.
    embeddings = encode_texts(add_embed_texts, batch_size=64)
    for i in range(0, len(add_ids), 200):
        collection.upsert(
            documents=add_docs[i : i + 200],
            embeddings=embeddings[i : i + 200],
            metadatas=add_metas[i : i + 200],
            ids=add_ids[i : i + 200],
        )
    for i in range(0, len(ids_to_delete), 500):
        collection.delete(ids=ids_to_delete[i : i + 500])
    print(f"Replaced {oversized} oversized chunks with {new_pieces} pieces.")

    try:
        from rag.bm25_index import rebuild_bm25_index
        rebuild_bm25_index()
        print("BM25 index rebuilt.")
    except Exception as exc:
        print(f"WARNING: BM25 rebuild failed: {exc}")
    try:
        from rag.cache import clear_all_caches
        clear_all_caches()
        print("Caches (Layer 1 & 2) cleared.")
    except Exception as exc:
        print(f"WARNING: cache clear failed: {exc}")


if __name__ == "__main__":
    main()
