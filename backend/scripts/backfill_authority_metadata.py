"""
scripts/backfill_authority_metadata.py

Backfill KNOWLEDGE HIERARCHY / authority metadata onto every chunk already in
the ChromaDB index. This is a METADATA-ONLY update — embeddings and chunk text
are never touched — so it is fast, safe, and idempotent (re-runnable).

It stamps each chunk with the fields derived by rag.authority.classify_document
(document_type, category, priority_level, authority_score, hostel_type,
display_name, version) plus the spec-named aliases section_heading / page_number,
so the existing 9k+ chunks gain the same authority metadata that new ingests get
automatically.

Run from the backend/ directory:
    .venv/bin/python scripts/backfill_authority_metadata.py            # dry run
    .venv/bin/python scripts/backfill_authority_metadata.py --apply    # write
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Allow running as a standalone script from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import collection, normalize_metadata  # noqa: E402
from rag.authority import classify_document  # noqa: E402

BATCH = 1000

_AUTHORITY_KEYS = (
    "document_type", "category", "priority_level", "authority_score",
    "hostel_type", "display_name", "version",
)


def _needs_update(meta: dict) -> tuple[bool, dict]:
    """Return (changed, new_meta) for one chunk."""
    derived = classify_document(meta)
    updates = dict(derived)
    updates.setdefault("section_heading", meta.get("section_title", ""))
    updates.setdefault("page_number", meta.get("page", 0))

    changed = False
    for key, value in updates.items():
        if str(meta.get(key, "")) != str(value):
            changed = True
            break
    if not changed:
        return False, meta

    new_meta = dict(meta)
    new_meta.update(updates)
    return True, normalize_metadata(new_meta)


def main(apply: bool) -> None:
    total = collection.count()
    print(f"[backfill] collection has {total} chunks (apply={apply})")

    offset = 0
    scanned = 0
    changed = 0
    by_priority: Counter = Counter()
    by_doc_type: Counter = Counter()

    while True:
        res = collection.get(include=["metadatas"], limit=BATCH, offset=offset)
        ids = res.get("ids", [])
        metas = res.get("metadatas", []) or []
        if not ids:
            break

        upd_ids: list[str] = []
        upd_metas: list[dict] = []

        for cid, meta in zip(ids, metas):
            scanned += 1
            meta = meta or {}
            need, new_meta = _needs_update(meta)
            final = new_meta if need else meta
            by_priority[str(final.get("priority_level", "standard"))] += 1
            by_doc_type[str(final.get("document_type", "general"))] += 1
            if need:
                changed += 1
                upd_ids.append(cid)
                upd_metas.append(new_meta)

        if apply and upd_ids:
            for i in range(0, len(upd_ids), BATCH):
                collection.update(
                    ids=upd_ids[i:i + BATCH],
                    metadatas=upd_metas[i:i + BATCH],
                )
            print(f"[backfill] updated {len(upd_ids)} chunks in batch @offset {offset}")

        offset += len(ids)
        if len(ids) < BATCH:
            break

    print("\n========== SUMMARY ==========")
    print(f"scanned   : {scanned}")
    print(f"to change : {changed}{'  (WRITTEN)' if apply else '  (dry run — pass --apply to write)'}")
    print(f"priority_level distribution : {dict(by_priority)}")
    print("document_type distribution  :")
    for k, v in by_doc_type.most_common():
        print(f"    {k:<14} {v}")

    # The BM25 index stores a metadata SNAPSHOT in data/bm25_index.pkl. A
    # metadata-only collection.update does NOT touch it, so the keyword path would
    # otherwise read stale metadata (e.g. document_type='general' for Tier 1 docs),
    # disagreeing with ChromaDB. Rebuild it from the freshly-updated collection and
    # invalidate the query caches so retrieval reflects the new metadata.
    if apply:
        print("\n[backfill] re-syncing BM25 index from ChromaDB (metadata snapshot)...")
        try:
            from rag.bm25_index import rebuild_bm25_index
            rebuild_bm25_index()
            print("[backfill] BM25 index rebuilt.")
        except Exception as exc:  # noqa: BLE001
            print(f"[backfill] WARNING: BM25 rebuild failed: {exc}")
        try:
            from rag.cache import invalidate_on_ingestion
            invalidate_on_ingestion()
            print("[backfill] query caches invalidated (Layers 1 & 2).")
        except Exception as exc:  # noqa: BLE001
            print(f"[backfill] WARNING: cache invalidation failed: {exc}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
