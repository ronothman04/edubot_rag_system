from __future__ import annotations

import os
import pickle
import logging
from typing import Any
from rank_bm25 import BM25Okapi
import db
from .text_utils import normalize_text, important_words, rerank_text

class EmptyBM25:
    def get_scores(self, query):
        return []


BM25_INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bm25_index.pkl")

# Global variables for in-memory index
_bm25_model: BM25Okapi | None = None
_bm25_docs: list[str] = []
_bm25_metas: list[dict] = []

def _tokenize(text: str) -> list[str]:
    return [w for w in normalize_text(text).split() if len(w) > 1]

def load_bm25_index():
    global _bm25_model, _bm25_docs, _bm25_metas
    if os.path.exists(BM25_INDEX_PATH):
        try:
            with open(BM25_INDEX_PATH, "rb") as f:
                data = pickle.load(f)
                _bm25_model = data["model"]
                _bm25_docs = data["docs"]
                _bm25_metas = data["metas"]
                logging.info(f"[BM25] Loaded index from disk with {len(_bm25_docs)} docs.")
        except Exception as e:
            logging.error(f"[BM25] Failed to load index: {e}")
            _bm25_model = None

def rebuild_bm25_index():
    global _bm25_model, _bm25_docs, _bm25_metas
    logging.info("[BM25] Rebuilding BM25 Index from ChromaDB...")
    
    try:
        result = db.collection.get(include=["documents", "metadatas"])
        docs = result.get("documents", [])
        metas = result.get("metadatas", [])
        
        if not docs:
            logging.info("[BM25] No documents found in ChromaDB. Creating empty index.")
            _bm25_model = EmptyBM25()
            _bm25_docs = []
            _bm25_metas = []
        else:
            # Tokenize from title-augmented text (section_title + filename + body)
            # so heading/title terms are searchable; store raw `docs` unchanged so
            # dedup keys and downstream scoring stay consistent.
            corpus_tokens = [
                _tokenize(rerank_text(doc, meta))
                for doc, meta in zip(docs, metas)
            ]
            _bm25_model = BM25Okapi(corpus_tokens)
            _bm25_docs = docs
            _bm25_metas = metas
        
        # Save to disk
        os.makedirs(os.path.dirname(BM25_INDEX_PATH), exist_ok=True)
        with open(BM25_INDEX_PATH, "wb") as f:
            pickle.dump({
                "model": _bm25_model,
                "docs": _bm25_docs,
                "metas": _bm25_metas
            }, f)
            
        logging.info(f"[BM25] Rebuild complete. Saved {len(docs)} docs to disk.")
    except Exception as e:
        logging.error(f"[BM25] Failed to rebuild BM25 index: {e}")

def bm25_retrieve(query: str, top_k: int = 50) -> tuple[list[str], list[dict], list[float]]:
    global _bm25_model, _bm25_docs, _bm25_metas
    if _bm25_model is None:
        load_bm25_index()
    if _bm25_model is None:
        logging.warning("[BM25] Index not available. Run rebuild_bm25_index().")
        return [], [], []

    query_tokens = _tokenize(query)
    scores = _bm25_model.get_scores(query_tokens)
    
    ranked = []
    for i, score in enumerate(scores):
        if score > 0:
            ranked.append((score, _bm25_docs[i], _bm25_metas[i]))
            
    ranked.sort(key=lambda x: x[0], reverse=True)
    
    selected = ranked[:top_k]
    return (
        [item[1] for item in selected],
        [item[2] for item in selected],
        [item[0] for item in selected]
    )

def get_all_documents_and_metas() -> tuple[list[str], list[dict]]:
    global _bm25_model, _bm25_docs, _bm25_metas
    if _bm25_model is None:
        load_bm25_index()
    return _bm25_docs, _bm25_metas

