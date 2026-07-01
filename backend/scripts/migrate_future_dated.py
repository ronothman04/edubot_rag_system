"""
migrate_future_dated.py

Document-scope correction for chunks whose ``document_year`` is in the FUTURE
relative to the runtime current year but is NOT a genuine publication/session
year (validity/expiry horizons, forward references, stray table numbers). Uses
the shared policy in ``rag.future_dates`` so it agrees exactly with
``scripts/audit_future_dated.py``.

Behaviour:
  * SUPPORTED / INFERRED_CREDIBLE (keep)  -> stamp document_year_audit="supported"
    so the query-time freshness guard trusts the future year (idempotent add).
  * demote classes                        -> set document_year to the document's
    best non-future year (or "general" when none), preserving the original value
    in document_year_original and recording document_year_audit. A future
    document_date (year > current year) is blanked so it cannot add a residual
    recency bonus.

Correction is applied at DOCUMENT scope: one true year per (filename, source_url)
document, written to every future-dated chunk of that document. Non-future chunks
are never touched.

Safety: metadata-only via collection.update — embeddings, documents, and chunk
IDs are unchanged; NO re-ingestion. Dry-run capable, snapshot-backed, bounded,
resumable (each document independent), and idempotent (a corrected chunk is no
longer future-dated, so a re-run skips it).

Usage:
    python -m scripts.migrate_future_dated            # dry-run report
    python -m scripts.migrate_future_dated --json     # dry-run, machine-readable
    python -m scripts.migrate_future_dated --apply    # perform migration
"""
from __future__ import annotations

import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def _plan(collection, current_year: int):
    """Build the per-chunk update plan (read-only). Returns (updates, summary)."""
    from rag.future_dates import classify_future_year

    got = collection.get(include=["documents", "metadatas"])

    # Group future-dated chunks by document identity.
    docs: dict[tuple, dict] = {}
    for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        meta = meta or {}
        try:
            dy = int(meta.get("document_year"))
        except (TypeError, ValueError):
            continue
        if dy <= current_year:
            continue
        key = (str(meta.get("filename", "")), str(meta.get("source_url", "")), dy)
        entry = docs.setdefault(key, {"ids": [], "metas": [], "text": []})
        entry["ids"].append(cid)
        entry["metas"].append(meta)
        entry["text"].append(doc)

    updates: list[tuple[str, dict]] = []  # (chunk_id, new_full_metadata)
    summary = {"documents": [], "totals": {}, "chunks_demoted": 0, "chunks_kept": 0}

    for (filename, source_url, dy), entry in docs.items():
        all_text = "\n".join(entry["text"])
        verdict = classify_future_year(dy, all_text, entry["metas"][0], current_year)
        cls = verdict["classification"]
        summary["totals"][cls] = summary["totals"].get(cls, 0) + 1

        for cid, meta in zip(entry["ids"], entry["metas"]):
            new_meta = dict(meta)
            if verdict["keep"]:
                if str(meta.get("document_year_audit", "")) == "supported":
                    continue  # already stamped -> idempotent no-op
                new_meta["document_year_audit"] = "supported"
                summary["chunks_kept"] += 1
            else:
                true_year = verdict["true_year"]
                new_meta["document_year_original"] = dy
                new_meta["document_year"] = true_year if true_year else "general"
                new_meta["document_year_audit"] = f"demoted:{cls}"
                # Blank a residual future document_date so it adds no recency bonus.
                dd = str(meta.get("document_date", "") or "")
                if dd[:4].isdigit() and int(dd[:4]) > current_year:
                    new_meta["document_date"] = ""
                summary["chunks_demoted"] += 1
            updates.append((cid, new_meta))

        summary["documents"].append({
            "document": filename, "source_url": source_url, "extracted_year": dy,
            "chunks": len(entry["ids"]), "classification": cls,
            "confidence": verdict["confidence"], "keep": verdict["keep"],
            "true_year": verdict["true_year"], "action": verdict["action"],
        })

    return updates, summary


def main() -> None:
    import logging
    logging.disable(logging.CRITICAL)

    from db import collection, normalize_metadata

    apply = "--apply" in sys.argv
    as_json = "--json" in sys.argv
    current_year = time.gmtime().tm_year

    updates, summary = _plan(collection, current_year)

    if as_json and not apply:
        print(json.dumps({"current_year": current_year, **summary}, indent=2, default=str))
        return

    print(f"=== Future-dated correction ({'APPLY' if apply else 'DRY-RUN'}) "
          f"— runtime year {current_year} ===")
    print(f"documents: {len(summary['documents'])}  "
          f"chunks to demote: {summary['chunks_demoted']}  "
          f"chunks to mark supported: {summary['chunks_kept']}")
    print(f"classification totals (documents): {summary['totals']}\n")
    for d in sorted(summary["documents"], key=lambda x: (x["keep"], -x["chunks"])):
        tag = "KEEP " if d["keep"] else f"DEMOTE->{d['true_year'] or 'general'}"
        print(f"  [{tag}] {d['document']}  x{d['chunks']}  "
              f"({d['classification']}/{d['confidence']})  {d['action']}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to perform the migration.")
        return
    if not updates:
        print("\nNothing to do.")
        return

    # Snapshot before this metadata-mutating migration.
    try:
        from scripts.migration_snapshot import create_snapshot
        create_snapshot("migrate_future_dated")
    except Exception as exc:
        print(f"[snapshot] WARNING: {exc}")

    ids = [cid for cid, _ in updates]
    metas = [normalize_metadata(m) for _, m in updates]
    for i in range(0, len(ids), 200):
        # Metadata-only: embeddings and documents are left intact.
        collection.update(ids=ids[i : i + 200], metadatas=metas[i : i + 200])
    print(f"\nUpdated metadata on {len(ids)} chunks (no re-embed, no id change).")

    # BM25 metas carry document_year; rebuild so keyword-retrieved candidates
    # also reflect the corrected years. Caches cleared so stale rankings are gone.
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
