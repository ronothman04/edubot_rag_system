"""
reranker.py - Local Cross-Encoder Reranker for EduBot

Uses:
- BAAI/bge-reranker-base

Purpose:
- Improve final chunk ranking after ChromaDB retrieval
- Works locally
- No API key required
- Falls back to keyword + distance scoring if model fails
"""

from __future__ import annotations

import os
import re
from typing import Any

USE_CROSS_ENCODER_RERANKER = (
    os.getenv("USE_CROSS_ENCODER_RERANKER", "true").lower() == "true"
)

CROSS_ENCODER_MODEL = os.getenv(
    "CROSS_ENCODER_MODEL",
    "BAAI/bge-reranker-base",
)

RERANKER_DEBUG = os.getenv("RERANKER_DEBUG", "false").lower() == "true"
MODEL_LOCAL_FILES_ONLY = (
    os.getenv("MODEL_LOCAL_FILES_ONLY", "true").strip().lower() == "true"
)

_cross_encoder_model = None
_cross_encoder_load_attempted = False


def _log_debug(message: str) -> None:
    if RERANKER_DEBUG:
        print(f"[EduBot Reranker] {message}")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9]+\b", str(text or "").lower())


def _local_score(query: str, doc: str, distance: float | None = None) -> float:
    """
    Safe fallback reranker.
    Higher score is better.
    """
    query_terms = _tokenize(query)
    doc_lower = str(doc or "").lower()
    query_lower = str(query or "").lower()

    score = 0.0

    for term in query_terms:
        if term in doc_lower:
            score += 1.0

    if query_lower and query_lower in doc_lower:
        score += 5.0

    if distance is not None:
        try:
            score += max(0.0, 1.0 - float(distance)) * 5.0
        except Exception:
            pass

    return score


def _fallback(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    top_n: int,
) -> tuple[list[str], list[dict], list[float]]:
    if not docs:
        return [], [], []

    ranked: list[tuple[float, int]] = []

    for i, doc in enumerate(docs):
        distance = dists[i] if i < len(dists) else None
        score = _local_score(query, doc, distance)
        ranked.append((score, i))

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected_indexes = [index for _score, index in ranked[:top_n]]

    return (
        [docs[i] for i in selected_indexes],
        [metas[i] for i in selected_indexes],
        [dists[i] for i in selected_indexes],
    )


def _get_cross_encoder():
    """
    Lazy-load model only when reranking is called.
    This prevents slow backend startup.
    """
    global _cross_encoder_model, _cross_encoder_load_attempted

    if _cross_encoder_model is not None:
        return _cross_encoder_model
    if _cross_encoder_load_attempted:
        return None

    _cross_encoder_load_attempted = True
    try:
        from sentence_transformers import CrossEncoder
        import torch

        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"

        print(f"[EduBot] Loading cross-encoder model on device: {device}")
        _cross_encoder_model = CrossEncoder(
            CROSS_ENCODER_MODEL,
            device=device,
            local_files_only=MODEL_LOCAL_FILES_ONLY,
        )
        return _cross_encoder_model

    except Exception as exc:
        _log_debug(f"Failed to load cross-encoder. Error: {exc}")
        return None


def cross_encoder_available() -> bool:
    """True when the cross-encoder reranker model is loaded and usable.

    When this is False, rerank_chunks_with_scores returns uniform fallback
    probabilities (~0.5) that the confidence gate cannot discriminate — callers
    should then fall back to a hard vector-distance gate to reject weak matches.
    """
    if not USE_CROSS_ENCODER_RERANKER:
        return False
    return _get_cross_encoder() is not None


def rerank_chunks_with_scores(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    top_n: int = 10,
) -> tuple[list[str], list[dict], list[float], list[float]]:
    """
    Rerank retrieved chunks using local cross-encoder.
    Returns (docs, metas, dists, reranker_scores) — scores are sigmoid probabilities.

    §3 Stage 7: Score every merged candidate against the FULL original query string.
    §7: Keep top-10 by reranker score.
    """

    if not docs:
        return [], [], [], []

    if not USE_CROSS_ENCODER_RERANKER:
        _log_debug("Cross-encoder disabled. Using fallback reranker.")
        fb_docs, fb_metas, fb_dists = _fallback(query, docs, metas, dists, top_n)
        return fb_docs, fb_metas, fb_dists, [0.5] * len(fb_docs)

    model = _get_cross_encoder()

    if model is None:
        _log_debug("Cross-encoder unavailable. Using fallback reranker.")
        fb_docs, fb_metas, fb_dists = _fallback(query, docs, metas, dists, top_n)
        return fb_docs, fb_metas, fb_dists, [0.5] * len(fb_docs)

    try:
        # Augment each chunk with its section title + filename (from metadata) so
        # the cross-encoder can see the heading/title, which is otherwise present
        # only in the dense embedding — not in the raw chunk body. No re-ingest.
        from rag.text_utils import rerank_text

        pairs = []

        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else None
            # Keep chunks short enough for reranker speed.
            clean_doc = rerank_text(doc, meta)[:1800]
            pairs.append((query, clean_doc))

        scores = model.predict(pairs)

        ranked: list[tuple[float, float, int]] = []  # (raw_score, sigmoid_prob, index)

        import math
        def sigmoid(x):
            try:
                return 1 / (1 + math.exp(-x))
            except OverflowError:
                return 0.0 if x < 0 else 1.0

        for i, score in enumerate(scores):
            try:
                s = float(score)
                prob = sigmoid(s)
                ranked.append((s, prob, i))
            except Exception:
                pass

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[:top_n]
        selected_indexes = [index for _score, _prob, index in selected]
        selected_probs = [prob for _score, prob, _index in selected]

        if RERANKER_DEBUG:
            for score, prob, index in selected:
                preview = str(docs[index] or "")[:160].replace("\n", " ")
                _log_debug(f"score={score:.4f} prob={prob:.4f} preview={preview}")

        return (
            [docs[i] for i in selected_indexes],
            [metas[i] for i in selected_indexes],
            [dists[i] for i in selected_indexes],
            selected_probs,
        )

    except Exception as exc:
        _log_debug(f"Cross-encoder reranking failed. Error: {exc}")
        fb_docs, fb_metas, fb_dists = _fallback(query, docs, metas, dists, top_n)
        return fb_docs, fb_metas, fb_dists, [0.5] * len(fb_docs)


def rerank_chunks(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    top_n: int = 10,
) -> tuple[list[str], list[dict], list[float]]:
    """
    Rerank retrieved chunks using local cross-encoder.
    Backward-compatible wrapper — returns (docs, metas, dists) without scores.
    """
    r_docs, r_metas, r_dists, _ = rerank_chunks_with_scores(
        query, docs, metas, dists, top_n
    )
    return r_docs, r_metas, r_dists

