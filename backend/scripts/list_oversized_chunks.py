"""
list_oversized_chunks.py  (READ-ONLY diagnostic)

Lists chunks whose embedding text still exceeds the embedding model's token cap
after the resplit migration. These are documented, not auto-split further — see
docs/ingestion_oversized_chunks.md. This script only reads; it never modifies the
store.

Usage:
    python -m scripts.list_oversized_chunks
"""
from __future__ import annotations

import collections
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main() -> None:
    import logging

    logging.disable(logging.CRITICAL)
    from db import collection
    from embeddings import get_embedding_model
    from ingestion import build_embedding_text

    model = get_embedding_model()
    tokenizer = model.tokenizer
    budget = int(getattr(model, "max_seq_length", 512) or 512)

    got = collection.get(include=["documents", "metadatas"])
    rows = []
    for doc, meta in zip(got["documents"], got["metadatas"]):
        meta = meta or {}
        # Measure the ACTUAL embedding text (header capped exactly as at ingest),
        # so this reflects real truncation rather than the pre-cap header length.
        et = build_embedding_text(doc, meta)
        n = len(tokenizer.encode(et))
        if n > budget:
            rows.append((n, str(meta.get("filename"))[:48], str(meta.get("chunk_type"))))

    rows.sort(reverse=True)
    print(f"embedding token budget: {budget}")
    print(f"chunks over budget    : {len(rows)} / {len(got['documents'])}")
    if rows:
        print(f"overflow range        : {rows[-1][0] - budget}..{rows[0][0] - budget} tokens over")
        by_type = collections.Counter(r[2] for r in rows)
        print(f"by chunk_type         : {dict(by_type)}")
        print("\n  tokens  chunk_type   filename")
        for n, fn, ct in rows:
            print(f"  {n:5}   {ct:10}  {fn}")


if __name__ == "__main__":
    main()
