import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent))

from db import reset_collection
from rag.bm25_index import rebuild_bm25_index

def clear_cache():
    print("[RESET] Resetting ChromaDB collection...")
    reset_collection(confirm=True)

    # Remove the pickled index file if it exists to be completely fresh
    index_pkl = Path(__file__).resolve().parent / "data" / "bm25_index.pkl"
    if index_pkl.exists():
        try:
            index_pkl.unlink()
            print("[RESET] Deleted old bm25_index.pkl")
        except Exception as e:
            print(f"[RESET] Failed to delete bm25_index.pkl: {e}")

    print("[RESET] Rebuilding BM25 index...")
    try:
        rebuild_bm25_index()
    except Exception as e:
        print(f"[RESET] BM25 Index rebuild failed: {e}")

    print("[RESET] Clearing uploads directory...")
    uploads_dir = Path(__file__).resolve().parent / "data" / "uploads"
    if uploads_dir.exists():
        for file in uploads_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                    print(f"  Deleted file: {file.name}")
                except Exception as e:
                    print(f"  Failed to delete file {file.name}: {e}")

    print("[RESET] Clearing crawl history...")
    crawl_jobs_file = Path(__file__).resolve().parent / "data" / "crawl_jobs.json"
    try:
        with open(crawl_jobs_file, "w") as f:
            f.write("{}")
        print("[RESET] Stored empty crawl jobs history.")
    except Exception as e:
        print(f"[RESET] Failed to clear crawl_jobs.json: {e}")

    print("[RESET] Complete! Cache cleared successfully.")

if __name__ == "__main__":
    clear_cache()
