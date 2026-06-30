"""
repair_crawl_url_pairing.py

One-off data repair for the crawler title<->source_url mismatch.

Root cause (now fixed in crawl4ai_crawler.py): `arun_many()` returns results in
COMPLETION order, but the crawler zipped them with the input URL list, pairing
each page's title/content with another page's URL. This stamped department /
programme chunks with the WRONG source_url (e.g. the "Computer Science
Department" page got the Education department URL).

This script recovers the CORRECT pairing for DEPARTMENT and PROGRAMME pages from
the data itself: every page's real URL is already present in the index (just
attached to the wrong title), so we re-derive the expected slug/path from the
reliable page title and only apply it when that target is in the set of URLs the
crawler actually visited. It never invents a URL — a page whose correct URL was
not crawled is left untouched.

Usage:
    python -m scripts.repair_crawl_url_pairing            # dry-run report
    python -m scripts.repair_crawl_url_pairing --apply    # write changes
"""
from __future__ import annotations

import os
import pickle
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

BM25_PATH = os.path.join(BASE_DIR, "data", "bm25_index.pkl")
DEPT_PREFIX = "/pages/departments/dept_"
PRGM_MARKER = "/pages/programmes/"

# Scraped page-title typos that do not slugify to the real URL slug.
_TITLE_SLUG_FIXUPS = {
    "bussiness_administration": "business_administration",
}

# URL fields that carry the (broken) page URL and must be repaired together.
_URL_FIELDS = ("source", "source_url", "url")

# --- Programme-page recovery -------------------------------------------------
# Maps a programme title prefix to the URL path it lives under. Degree-only
# programmes (BBA, MCA) have a fixed full path; subject-bearing ones append the
# slugified subject. M.Sc./M.A. live under /pg/.
_PRGM_DEGREES = (
    ("b.a.", "ug/ba", "ug_ba", False),
    ("b.sc.", "ug/bsc", "ug_bsc", False),
    ("b.com.", "ug/bcom", "ug_bcom", False),
    ("m.sc.", "pg", "pg_msc", False),
    ("m.a.", "pg", "pg_ma", False),
)
# Fixed full paths (degree-only or special pages).
_PRGM_FIXED = (
    ("b.b.a.", "ug/bba/prgm_ug_bba"),
    ("m.c.a.", "pg/prgm_pg_mca"),
    ("certificate courses", "dc/prgm_dc_cc"),
    ("tally", "dc/prgm_dc_tally"),
)
# Multi-word subjects whose plain slugify does not match the real URL slug.
_PRGM_SUBJECT_ALIASES = {
    "mass communication video production": "mcvp",
    "media technologies": "media_tech",
    "accounting finance": "account_finance",
    "banking insurance": "banking_insurance",
}


def _prgm_path_from_url(url: str) -> str | None:
    """Path under /pages/programmes/ minus the .php suffix, or None."""
    if PRGM_MARKER not in (url or ""):
        return None
    tail = url.split(PRGM_MARKER, 1)[1]
    return tail.split(".php", 1)[0] or None


def _prgm_path_from_title(title: str) -> str | None:
    """Reconstruct the expected programme path from the page title, or None when
    the title is not a recognisable programme page."""
    t = (title or "").lower().split("|")[0].strip()
    if not t:
        return None
    for prefix, fixed_path in _PRGM_FIXED:
        if t.startswith(prefix) or prefix in t:
            return fixed_path
    for prefix, level_dir, slug_prefix, _ in _PRGM_DEGREES:
        if not t.startswith(prefix):
            continue
        subject = t[len(prefix):]
        subject = re.sub(r"[^a-z0-9]+", " ", subject.replace("&", " ")).strip()
        if not subject:
            return None
        subject = _PRGM_SUBJECT_ALIASES.get(subject, subject.replace(" ", "_"))
        return f"{level_dir}/prgm_{slug_prefix}_{subject}"
    return None


def _dept_slug_from_title(title: str) -> str | None:
    """Derive the department URL slug from a '<Subject> Department | ...' title."""
    t = (title or "").lower().split("|")[0]
    if "department" not in t:
        return None
    t = re.sub(r"\bdepartment\b", " ", t)
    slug = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return _TITLE_SLUG_FIXUPS.get(slug, slug) or None


def _dept_slug_from_url(url: str) -> str | None:
    if DEPT_PREFIX not in (url or ""):
        return None
    return url.split(DEPT_PREFIX, 1)[1].split(".php", 1)[0] or None


def _build_pool(all_metas) -> dict[str, set[str]]:
    """Sets of department slugs and programme paths the crawler actually visited
    (verified targets). Recovery only ever points at a member of these sets."""
    dept: set[str] = set()
    prgm: set[str] = set()
    for meta in all_metas:
        for field in _URL_FIELDS:
            url = str((meta or {}).get(field) or "")
            slug = _dept_slug_from_url(url)
            if slug:
                dept.add(slug)
            path = _prgm_path_from_url(url)
            if path:
                prgm.add(path)
    return {"dept": dept, "prgm": prgm}


def _correct_url_for(meta: dict, pool: dict[str, set[str]]) -> tuple[str, str] | None:
    """Return (old_url, correct_url) when this chunk's dept/programme URL is wrong
    and the correct target was actually crawled, else None."""
    meta = meta or {}
    old_url = str(meta.get("source_url") or "")
    title = str(meta.get("filename") or meta.get("title") or "")

    # Department pages.
    cur_slug = _dept_slug_from_url(old_url)
    if cur_slug:
        want_slug = _dept_slug_from_title(title)
        if not want_slug or want_slug == cur_slug:
            return None
        if want_slug not in pool["dept"]:
            return None  # safety: only ever point at a URL the crawler visited
        return old_url, old_url.replace(f"dept_{cur_slug}.php", f"dept_{want_slug}.php")

    # Programme pages.
    cur_path = _prgm_path_from_url(old_url)
    if cur_path:
        want_path = _prgm_path_from_title(title)
        if not want_path or want_path == cur_path:
            return None
        if want_path not in pool["prgm"]:
            return None  # safety: target page was not crawled — do not fabricate
        base = old_url.split(PRGM_MARKER, 1)[0] + PRGM_MARKER
        return old_url, f"{base}{want_path}.php"

    return None


def _apply_to_meta(meta: dict, old_url: str, correct_url: str) -> None:
    for field in _URL_FIELDS:
        if str(meta.get(field) or "") == old_url:
            meta[field] = correct_url


def repair_bm25(apply: bool) -> int:
    with open(BM25_PATH, "rb") as fh:
        data = pickle.load(fh)
    metas = data.get("metas", [])
    pool = _build_pool(metas)
    changed = 0
    for meta in metas:
        fix = _correct_url_for(meta, pool)
        if not fix:
            continue
        old_url, correct_url = fix
        changed += 1
        print(f"  [bm25] {meta.get('filename','')[:40]!r}\n         {old_url}\n      -> {correct_url}")
        if apply:
            _apply_to_meta(meta, old_url, correct_url)
    if apply and changed:
        with open(BM25_PATH, "wb") as fh:
            pickle.dump(data, fh)
    return changed


def repair_chroma(apply: bool) -> int:
    import logging

    logging.disable(logging.CRITICAL)
    from db import collection

    got = collection.get(include=["metadatas"])
    ids = got["ids"]
    metas = got["metadatas"]
    pool = _build_pool(metas)

    upd_ids, upd_metas = [], []
    for cid, meta in zip(ids, metas):
        fix = _correct_url_for(meta, pool)
        if not fix:
            continue
        old_url, correct_url = fix
        print(f"  [chroma] {meta.get('filename','')[:40]!r}\n         {old_url}\n      -> {correct_url}")
        _apply_to_meta(meta, old_url, correct_url)
        upd_ids.append(cid)
        upd_metas.append(meta)

    if apply and upd_ids:
        # Update in batches to stay within Chroma limits.
        for i in range(0, len(upd_ids), 200):
            collection.update(ids=upd_ids[i : i + 200], metadatas=upd_metas[i : i + 200])
    return len(upd_ids)


def main() -> None:
    apply = "--apply" in sys.argv
    print(f"=== Crawl URL-pairing repair ({'APPLY' if apply else 'DRY-RUN'}) ===")
    if apply:
        try:
            from scripts.migration_snapshot import create_snapshot
            create_snapshot("repair_crawl_url_pairing")
        except Exception as exc:
            print(f"[snapshot] WARNING: {exc}")
    print("\n-- BM25 index --")
    n_bm25 = repair_bm25(apply)
    print("\n-- ChromaDB --")
    n_chroma = repair_chroma(apply)
    print(f"\nSummary: bm25 chunks={n_bm25}, chroma chunks={n_chroma}, applied={apply}")
    if apply:
        try:
            import logging

            logging.disable(logging.CRITICAL)
            from rag.cache import clear_all_caches

            clear_all_caches()
            print("Caches (Layer 1 & 2) cleared.")
        except Exception as exc:  # pragma: no cover
            print(f"WARNING: cache clear failed: {exc}")


if __name__ == "__main__":
    main()
