"""
rag/cache.py
Multi-layer cache system for St. Anthony's College EduBot RAG pipeline.
Aligned with specification §8 — Caching Strategy.

Layer 1 — Response cache:   SHA-256(normalized_query) → final LLM response, TTL 24h
Layer 2 — Retrieval cache:  SHA-256(normalized_query + intent_label) → ranked chunk IDs, TTL 1h
Layer 3 — Embedding cache:  (handled by sentence-transformers disk cache, permanent until model changes)

Cache invalidation:
  - Run ingestion → purge Layer 1 and Layer 2 entirely
  - Upgrade embedding model → purge Layer 3 entirely (out of scope here)
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from .text_utils import normalize_query


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
)

RESPONSE_CACHE_FILE = os.path.join(CACHE_DIR, "response_cache.json")
RETRIEVAL_CACHE_FILE = os.path.join(CACHE_DIR, "retrieval_cache.json")

# Increment when retrieval/answer semantics change so deployed processes cannot
# keep serving responses produced by an older pipeline for the duration of TTL.
CACHE_SCHEMA_VERSION = "3"

# Import TTLs from config (with fallback defaults)
try:
    from .config import RESPONSE_CACHE_TTL, RETRIEVAL_CACHE_TTL
except ImportError:
    RESPONSE_CACHE_TTL = 86400   # 24 hours
    RETRIEVAL_CACHE_TTL = 3600   # 1 hour


# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY STORES
# ═══════════════════════════════════════════════════════════════════════════════

_response_cache: Dict[str, Any] = {}       # Layer 1
_retrieval_cache: Dict[str, Any] = {}      # Layer 2
_response_cache_loaded = False
_retrieval_cache_loaded = False


# ═══════════════════════════════════════════════════════════════════════════════
# KEY GENERATION (§3 Stage 2: SHA-256 hash of normalized query)
# ═══════════════════════════════════════════════════════════════════════════════

def _sha256(text: str) -> str:
    """Generate SHA-256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _history_signature(filters: Dict[str, Any] | None) -> str:
    """Stable hash of the conversation history a follow-up depends on.

    Empty/absent history → empty signature, so standalone questions keep the
    SAME key as before (cross-user cache sharing is preserved). When history is
    present the key becomes conversation-specific, so a vague follow-up like
    "what about the fees?" can never be served another conversation's cached
    answer (the previous key was SHA-256 of the query text alone).
    """
    history = ""
    if filters:
        history = str(filters.get("history") or "")
    history = normalize_query(history)
    return _sha256(history) if history else ""


def _scope_signature(filters: Dict[str, Any] | None) -> str:
    """Stable hash of the RETRIEVAL SCOPE a cached answer depends on.

    Without this, two requests with the same query text but DIFFERENT scope
    (personal vs official docs, or a different department/year/document_type
    filter) collided on the same cache key and could be served each other's
    documents. The common public case — official scope, no explicit filters —
    returns "" so cross-user cache sharing for ordinary questions is preserved
    (a standalone official question keeps a scope-independent key).
    """
    if not filters:
        return ""
    parts: list[str] = []
    if filters.get("use_personal_docs"):
        # Personal docs are user-private: bind the key to the owner.
        parts.append("personal")
        parts.append(str(filters.get("user_id") or ""))
    for key in ("department", "year", "document_type"):
        value = filters.get(key)
        if value and str(value).strip().lower() not in ("", "general", "none"):
            parts.append(f"{key}={str(value).strip().lower()}")
    return _sha256("|".join(parts)) if parts else ""


def retrieval_scope_label(where_filter: Dict[str, Any] | None, use_personal_docs: bool = False) -> str:
    """Scope component for the Layer-2 retrieval cache key.

    The retrieval layer only sees the resolved ``where_filter`` + the personal
    flag (not the raw request fields), so we hash those directly. Default
    (official scope, no filter) → the literal "official" so ordinary questions
    keep a stable, shareable key.
    """
    parts: list[str] = []
    if use_personal_docs:
        parts.append("personal")
    if where_filter:
        try:
            parts.append(json.dumps(where_filter, sort_keys=True, ensure_ascii=False))
        except Exception:
            parts.append(str(where_filter))
    if not parts:
        return "official"
    return _sha256("|".join(parts))


def _response_cache_key(query: str, filters: Dict[str, Any] | None = None) -> str:
    """§8 Layer 1 key: SHA-256(normalized_query + conversation signature + scope)"""
    norm_q = normalize_query(query)
    sig = _history_signature(filters)
    scope = _scope_signature(filters)
    return _sha256(f"{CACHE_SCHEMA_VERSION}|{norm_q}|{sig}|{scope}")


def _retrieval_cache_key(query: str, intent_label: str = "") -> str:
    """§8 Layer 2 key: SHA-256(normalized_query + intent_label).

    intent_label already carries top_k, embedding model, AND the retrieval scope
    (see retrieval.py, which folds in retrieval_scope_label)."""
    norm_q = normalize_query(query)
    combined = f"{CACHE_SCHEMA_VERSION}|{norm_q}|{intent_label}"
    return _sha256(combined)


# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def _load_json_cache(filepath: str) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[RAG Cache] Failed to load {filepath}: {e}")
    return {}


def _save_json_cache(filepath: str, data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"[RAG Cache] Failed to save {filepath}: {e}")


def _ensure_response_cache_loaded() -> None:
    global _response_cache, _response_cache_loaded
    if not _response_cache_loaded:
        _response_cache = _load_json_cache(RESPONSE_CACHE_FILE)
        _response_cache_loaded = True


def _ensure_retrieval_cache_loaded() -> None:
    global _retrieval_cache, _retrieval_cache_loaded
    if not _retrieval_cache_loaded:
        _retrieval_cache = _load_json_cache(RETRIEVAL_CACHE_FILE)
        _retrieval_cache_loaded = True


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — RESPONSE CACHE
# ═══════════════════════════════════════════════════════════════════════════════

def get_cached_response(query: str, filters: Dict[str, Any] | None = None) -> Optional[Dict[str, Any]]:
    """
    §3 Stage 3: Cache lookup.
    If cache HIT: return cached response immediately.
    If cache MISS: return None.
    """
    _ensure_response_cache_loaded()
    key = _response_cache_key(query, filters)

    entry = _response_cache.get(key)
    if entry is None:
        return None

    # Check TTL
    stored_at = entry.get("_cached_at", 0)
    if time.time() - stored_at > RESPONSE_CACHE_TTL:
        # Expired — remove and return miss
        _response_cache.pop(key, None)
        logging.info(f"[RAG Cache] Layer 1 expired for query: '{query[:80]}'")
        return None

    logging.info(f"[RAG Cache] Layer 1 HIT for query: '{query[:80]}'")
    response = entry.get("response")
    return response


def set_cached_response(query: str, filters: Dict[str, Any] | None, response: Dict[str, Any]) -> None:
    """
    §3 Stage 10: On success, store response in cache under hash key.
    """
    # Do not cache error responses or rate-limiting/busy messages. NOT_FOUND is
    # also never cached: a transient "couldn't find it" must not be served for
    # 24h after the relevant document is added/re-ingested.
    if response.get("response_type") in ("error", "not_found") or "error" in response:
        return

    answer = response.get("answer", "")
    if "temporarily busy" in answer or "please try again in 30 seconds" in answer.lower():
        return

    _ensure_response_cache_loaded()
    key = _response_cache_key(query, filters)
    _response_cache[key] = {
        "response": response,
        "_cached_at": time.time(),
    }
    _save_json_cache(RESPONSE_CACHE_FILE, _response_cache)
    logging.info(f"[RAG Cache] Layer 1 stored for query: '{query[:80]}'")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — RETRIEVAL CACHE
# ═══════════════════════════════════════════════════════════════════════════════

def get_cached_retrieval(query: str, intent_label: str = "") -> Optional[list]:
    """
    §8 Layer 2: Retrieve cached (chunk_id, reranker_score) pairs.
    """
    _ensure_retrieval_cache_loaded()
    key = _retrieval_cache_key(query, intent_label)

    entry = _retrieval_cache.get(key)
    if entry is None:
        return None

    stored_at = entry.get("_cached_at", 0)
    if time.time() - stored_at > RETRIEVAL_CACHE_TTL:
        _retrieval_cache.pop(key, None)
        logging.info(f"[RAG Cache] Layer 2 expired for query: '{query[:80]}'")
        return None

    logging.info(f"[RAG Cache] Layer 2 HIT for query: '{query[:80]}'")
    return entry.get("results")


def set_cached_retrieval(query: str, intent_label: str, results: list) -> None:
    """
    §8 Layer 2: Cache ordered list of (chunk_id, reranker_score) pairs.
    """
    _ensure_retrieval_cache_loaded()
    key = _retrieval_cache_key(query, intent_label)
    _retrieval_cache[key] = {
        "results": results,
        "_cached_at": time.time(),
    }
    _save_json_cache(RETRIEVAL_CACHE_FILE, _retrieval_cache)
    logging.info(f"[RAG Cache] Layer 2 stored for query: '{query[:80]}'")


# ═══════════════════════════════════════════════════════════════════════════════
# INVALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def invalidate_on_ingestion() -> None:
    """
    §8: Run ingestion → purge Layer 1 and Layer 2 entirely.
    Never purge Layer 3 on ingestion (embeddings are model-dependent, not data-dependent).
    """
    global _response_cache, _retrieval_cache
    _response_cache = {}
    _retrieval_cache = {}
    _save_json_cache(RESPONSE_CACHE_FILE, _response_cache)
    _save_json_cache(RETRIEVAL_CACHE_FILE, _retrieval_cache)
    logging.info("[RAG Cache] Layers 1 & 2 invalidated (ingestion)")


def clear_all_caches() -> None:
    """Utility: clear everything (for debugging / admin)."""
    invalidate_on_ingestion()
