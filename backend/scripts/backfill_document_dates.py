"""
backfill_document_dates.py

Corrects the fabricated publication dates left by the old ingestion code, which
stamped EVERY undated chunk with document_year=2026 and document_date=2026-06-12.
That fake "freshest" stamp defeats rag/freshness.py (which is designed to treat an
unknown year as "no recency boost") and corrupts authority/conflict resolution
for "current"/"latest" questions.

This migration recomputes each chunk's document_year from TRUSTED identifier
fields only — filename / title / source_url / year / real date fields — never the
poisoned document_year, never body text, never the crawl timestamp. When no real
year can be derived it stores the honest sentinel "general" (and clears the fake
"2026-06-12" date to ""). Update-only: it never deletes chunks.

Usage:
    python -m scripts.backfill_document_dates            # dry-run report
    python -m scripts.backfill_document_dates --apply    # write changes
"""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# The exact fabricated values the old code wrote.
_FAKE_YEAR = 2026
_FAKE_DATE = "2026-06-12"

# Real (publication) date fields, in order of trust. crawl_timestamp is
# deliberately EXCLUDED: a crawl date is not a publication date.
_REAL_DATE_KEYS = (
    "document_date", "date", "ModDate", "CreationDate",
    "last_modified", "Last-Modified",
)


def _trusted_year(meta: dict) -> int | None:
    """Year derived only from identifier/date fields, ignoring the (poisoned)
    document_year and any body text."""
    from rag.freshness import document_year_from_metadata

    probe = dict(meta or {})
    probe.pop("document_year", None)  # ignore the fabricated stamp
    # Don't let the fake date masquerade as a real one.
    if str(probe.get("document_date") or "").strip() == _FAKE_DATE:
        probe.pop("document_date", None)
    return document_year_from_metadata(probe)


def _trusted_date(meta: dict) -> str:
    """Real publication date from trusted fields only (never crawl_timestamp,
    never the fabricated sentinel)."""
    from rag.freshness import parse_document_date_value

    for key in _REAL_DATE_KEYS:
        val = str((meta or {}).get(key) or "").strip()
        if not val or val == _FAKE_DATE:
            continue
        parsed = parse_document_date_value(val)
        if parsed:
            return parsed
    return ""


def _corrected(meta: dict) -> dict | None:
    """Return {field: new_value} for fields that should change, or None."""
    meta = meta or {}
    changes: dict = {}

    cur_year = str(meta.get("document_year"))
    # Only touch chunks currently carrying the fabricated stamp (or an explicit
    # unknown), so genuinely-extracted years are never disturbed.
    if cur_year == str(_FAKE_YEAR) or cur_year.strip().lower() in ("", "general", "none", "null"):
        derived = _trusted_year(meta)
        new_year = derived if derived else "general"
        if str(new_year) != cur_year:
            changes["document_year"] = new_year

    cur_date = str(meta.get("document_date") or "")
    if cur_date == _FAKE_DATE:
        changes["document_date"] = _trusted_date(meta)  # real date or ""

    return changes or None


def main() -> None:
    import logging

    logging.disable(logging.CRITICAL)
    from db import collection, normalize_metadata

    apply = "--apply" in sys.argv
    print(f"=== Document date backfill ({'APPLY' if apply else 'DRY-RUN'}) ===")

    got = collection.get(include=["metadatas"])
    ids = got["ids"]
    metas = got["metadatas"]

    upd_ids, upd_metas = [], []
    year_to_general = 0
    year_recovered = 0
    date_cleared = 0
    for cid, meta in zip(ids, metas):
        changes = _corrected(meta)
        if not changes:
            continue
        if "document_year" in changes:
            if changes["document_year"] == "general":
                year_to_general += 1
            else:
                year_recovered += 1
        if changes.get("document_date") == "":
            date_cleared += 1
        new_meta = normalize_metadata({**(meta or {}), **changes})
        upd_ids.append(cid)
        upd_metas.append(new_meta)

    print(f"chunks needing correction : {len(upd_ids)} / {len(ids)}")
    print(f"  year recovered from id   : {year_recovered}")
    print(f"  year -> 'general' (honest unknown): {year_to_general}")
    print(f"  fabricated date cleared  : {date_cleared}")

    if apply and upd_ids:
        try:
            from scripts.migration_snapshot import create_snapshot
            create_snapshot("backfill_document_dates")
        except Exception as exc:
            print(f"[snapshot] WARNING: {exc}")
        for i in range(0, len(upd_ids), 200):
            collection.update(ids=upd_ids[i : i + 200], metadatas=upd_metas[i : i + 200])
        print(f"Applied {len(upd_ids)} updates to ChromaDB.")
        try:
            from rag.bm25_index import rebuild_bm25_index
            rebuild_bm25_index()
            print("BM25 index rebuilt from corrected metadata.")
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
