"""
reembed_oversized_header_chunks.py

Targeted (NOT full) re-embed migration for chunks whose *body already fits* the
embedding model's 512-token cap but whose ``Title/Source/Section`` header was so
long (measured 51-119 tokens vs. a 48-token reserve) that the FULL embedding text
overflowed and SentenceTransformer silently truncated the body tail from the
vector.

The forward fix (ingestion.build_embedding_text) caps the header at ingest time.
This script repairs the EXISTING affected chunks by re-embedding them IN PLACE
with the header-capped embedding text — same chunk id, same document text, same
metadata, only a corrected vector. It is idempotent (re-running yields the same
vector), reversible (a snapshot is taken before --apply), and bounded.

It deliberately does NOT touch chunks whose *body* is itself oversized — those
are handled by scripts/resplit_oversized_chunks.py (which splits the body).

IMPACT (read before --apply):
  * Only chunks whose uncapped full embedding text > cap AND whose capped text
    <= cap are re-embedded. All others are untouched.
  * ~28 chunks at last measurement; a few seconds of CPU embedding.
  * IDs, document text, and metadata are unchanged; upsert replaces the vector.
  * A snapshot is taken before applying; caches are cleared at the end. BM25 is
    unaffected (indexes document text, which does not change) and left as-is.

Usage:
    python -m scripts.reembed_oversized_header_chunks            # dry-run report
    python -m scripts.reembed_oversized_header_chunks --apply    # perform migration
"""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main() -> None:
    import logging

    logging.disable(logging.CRITICAL)

    from db import collection
    from embeddings import get_embedding_model, encode_texts
    from ingestion import build_embedding_text

    apply = "--apply" in sys.argv
    print(f"=== Re-embed long-header oversized chunks ({'APPLY' if apply else 'DRY-RUN'}) ===")

    model = get_embedding_model()
    tokenizer = model.tokenizer
    cap = int(getattr(model, "max_seq_length", 512) or 512)

    got = collection.get(include=["documents", "metadatas"])
    ids = got["ids"]
    docs = got["documents"]
    metas = got["metadatas"]

    fix_ids: list[str] = []
    fix_docs: list[str] = []
    fix_embed_texts: list[str] = []
    fix_metas: list[dict] = []
    body_oversized = 0  # chunks the header cap alone cannot save (body too long)

    def _uncapped(doc: str, meta: dict) -> str:
        return (
            f"Title: {meta.get('title', '')}\n"
            f"Source: {meta.get('filename', '')}\n"
            f"Section: {meta.get('heading', '')}\n\n{doc}"
        )

    for cid, doc, meta in zip(ids, docs, metas):
        meta = meta or {}
        uncapped_tokens = len(tokenizer.encode(_uncapped(doc, meta), add_special_tokens=True))
        if uncapped_tokens <= cap:
            continue  # never truncated
        capped_text = build_embedding_text(doc, meta)
        capped_tokens = len(tokenizer.encode(capped_text, add_special_tokens=True))
        if capped_tokens > cap:
            # Header cap alone is not enough — the body itself overflows.
            body_oversized += 1
            continue
        fix_ids.append(cid)
        fix_docs.append(doc)
        fix_embed_texts.append(capped_text)
        fix_metas.append(meta)

    print(f"embedding cap                     : {cap} tokens")
    print(f"long-header chunks to re-embed    : {len(fix_ids)}")
    print(f"body-oversized (defer to resplit) : {body_oversized}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to perform the migration.")
        return
    if not fix_ids:
        print("Nothing to do.")
        return

    # Snapshot before this vector-mutating migration.
    try:
        from scripts.migration_snapshot import create_snapshot
        create_snapshot("reembed_oversized_header_chunks")
    except Exception as exc:
        print(f"[snapshot] WARNING: {exc}")

    embeddings = encode_texts(fix_embed_texts, batch_size=64)
    for i in range(0, len(fix_ids), 200):
        # In-place: same ids/documents/metadatas, corrected embeddings only.
        collection.upsert(
            ids=fix_ids[i : i + 200],
            documents=fix_docs[i : i + 200],
            embeddings=embeddings[i : i + 200],
            metadatas=fix_metas[i : i + 200],
        )
    print(f"Re-embedded {len(fix_ids)} chunks in place with capped headers.")

    try:
        from rag.cache import clear_all_caches
        clear_all_caches()
        print("Caches (Layer 1 & 2) cleared.")
    except Exception as exc:
        print(f"WARNING: cache clear failed: {exc}")


if __name__ == "__main__":
    main()
