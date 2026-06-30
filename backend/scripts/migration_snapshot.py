"""
migration_snapshot.py

Backup / snapshot mechanism for the EduBot vector store. Call create_snapshot()
BEFORE any destructive or hard-to-reverse data migration (chunk re-split, metadata
backfill, URL repair) so the exact pre-migration state can be restored.

A snapshot copies the two stateful artifacts:
  * the ChromaDB directory (backend/chroma_db)
  * the BM25 index pickle (backend/data/bm25_index.pkl)
into backend/data/backups/<UTC-timestamp>_<label>/.

It never deletes or mutates live data. Restore is an explicit, manual step.

CLI:
    python -m scripts.migration_snapshot create [label]
    python -m scripts.migration_snapshot list
    python -m scripts.migration_snapshot restore <snapshot_dir_name>   # asks to confirm
"""
from __future__ import annotations

import os
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
BM25_PATH = os.path.join(BASE_DIR, "data", "bm25_index.pkl")
BACKUPS_DIR = os.path.join(BASE_DIR, "data", "backups")


def _safe_label(label: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (label or "snapshot"))[:60]


def create_snapshot(label: str = "snapshot") -> str:
    """Copy ChromaDB + BM25 index into a timestamped backup dir. Returns its path.
    Best-effort and non-fatal: a failure to snapshot is reported but never raises,
    so it cannot block a migration the operator chose to run."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = os.path.join(BACKUPS_DIR, f"{stamp}_{_safe_label(label)}")
    try:
        os.makedirs(dest, exist_ok=True)
        if os.path.isdir(CHROMA_DIR):
            shutil.copytree(CHROMA_DIR, os.path.join(dest, "chroma_db"), dirs_exist_ok=True)
        if os.path.isfile(BM25_PATH):
            os.makedirs(os.path.join(dest, "data"), exist_ok=True)
            shutil.copy2(BM25_PATH, os.path.join(dest, "data", "bm25_index.pkl"))
        with open(os.path.join(dest, "MANIFEST.txt"), "w") as fh:
            fh.write(f"label={label}\ncreated_utc={stamp}\nchroma_dir={CHROMA_DIR}\nbm25={BM25_PATH}\n")
        print(f"[snapshot] created: {dest}")
        return dest
    except Exception as exc:  # pragma: no cover - disk/IO failure
        print(f"[snapshot] WARNING: snapshot failed ({exc}); proceeding without backup.")
        return ""


def list_snapshots() -> list[str]:
    if not os.path.isdir(BACKUPS_DIR):
        return []
    return sorted(d for d in os.listdir(BACKUPS_DIR) if os.path.isdir(os.path.join(BACKUPS_DIR, d)))


def restore_snapshot(name: str) -> bool:
    """Restore a snapshot over the live store. Caller must confirm; this overwrites
    chroma_db and bm25_index.pkl. The current live state is itself snapshotted
    first (label 'pre_restore') so a restore is also reversible."""
    src = os.path.join(BACKUPS_DIR, name)
    if not os.path.isdir(src):
        print(f"[snapshot] no such snapshot: {name}")
        return False
    create_snapshot("pre_restore")
    src_chroma = os.path.join(src, "chroma_db")
    if os.path.isdir(src_chroma):
        if os.path.isdir(CHROMA_DIR):
            shutil.rmtree(CHROMA_DIR)
        shutil.copytree(src_chroma, CHROMA_DIR)
    src_bm25 = os.path.join(src, "data", "bm25_index.pkl")
    if os.path.isfile(src_bm25):
        os.makedirs(os.path.dirname(BM25_PATH), exist_ok=True)
        shutil.copy2(src_bm25, BM25_PATH)
    print(f"[snapshot] restored from {src}. Restart the app to load the restored index.")
    return True


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    if cmd == "create":
        create_snapshot(args[1] if len(args) > 1 else "manual")
    elif cmd == "list":
        snaps = list_snapshots()
        print("Snapshots:" if snaps else "No snapshots yet.")
        for s in snaps:
            print("  ", s)
    elif cmd == "restore":
        if len(args) < 2:
            print("usage: python -m scripts.migration_snapshot restore <snapshot_dir_name>")
            return
        if input(f"Restore '{args[1]}' over live data? [y/N] ").strip().lower() == "y":
            restore_snapshot(args[1])
        else:
            print("aborted.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
