from __future__ import annotations

"""
rag/debug.py
Diagnostics and pipeline search preview helpers for St. Anthony's College EduBot.
Imports config.py, filters.py, scoring.py, intent.py, query_expansion.py, retrieval.py, context.py, answer_builders.py,
and external db.py and embeddings.py.
"""

from typing import Any
import re

from db import collection
from embeddings import encode_query

from .config import (
    DEBUG_RAG,
    DEFAULT_TOP_K,
    MAX_DISTANCE,
)
from .text_utils import (
    clean_text,
    normalize_text,
    normalize_query,
    content_without_context_header,
)
from .filters import (
    build_filter,
    candidate_dedupe_key,
    metadata_allows_query,
)
from .scoring import (
    keyword_score,
    admission_evidence_score,
    role_evidence_score,
    document_evidence_score,
    fee_evidence_score,
    hostel_evidence_score,
    is_toc_candidate,
    metadata_boost_score,
    hostel_relevance_score,
    procedural_relevance_score,
    person_lookup_relevance_score,
    _criteria_heading_for_query,
)
from .intent import (
    classify_admission_query,
    get_requested_person_title,
    is_person_lookup_query,
    is_hostel_query,
    is_procedural_query,
    is_fee_query,
    is_contact_query,
    is_attendance_query,
    is_criteria_query,
    is_club_query,
    is_cell_or_committee_query,
    is_activity_query,
    is_staff_query,
    is_head_query,
    is_specific_query,
    is_document_overview_query,
    is_website_links_query,
    extract_role_query,
    extract_query_target,
    extract_exact_topic,
    build_generic_retrieval_query,
)
from .query_expansion import (
    expand_query,
    build_smart_retrieval_query,
)
from .retrieval import (
    keyword_retrieve_chunks,
    vector_retrieve_chunks,
    special_list_keyword_retrieve,
    rerank_results,
    retrieve_chunks,
)
from .context import build_context



def debug_rag(message: str, *values: Any) -> None:
    if not DEBUG_RAG:
        return
    print(f"[DEBUG_RAG] {message}", *values)


def debug_print_chunks(
    query: str,
    docs: list[str],
    metas: list[dict],
    scores: list[Any] | None = None,
    title: str = "RETRIEVED CHUNKS",
) -> None:
    if not DEBUG_RAG:
        return

    print("\n" + "=" * 80)
    print(title)
    print("QUERY:", query)
    print("=" * 80)

    for i, doc in enumerate(docs[:10]):
        meta = metas[i] if i < len(metas) else {}
        score = scores[i] if scores and i < len(scores) else None

        print(f"\n--- CHUNK {i + 1} ---")
        print("Score:", score)
        print("Filename:", (meta or {}).get("filename"))
        print("Page:", (meta or {}).get("page"))
        print("Section:", (meta or {}).get("section_title"))
        print("Snippet:", clean_text(str(doc or ""))[:350] + "...")
    print("=" * 80 + "\n")


# TODO: split
def debug_search_chunks(query: str, top_k: int = 10) -> dict[str, Any]:
    """
    Admin/debug helper that probes Chroma and the normal hybrid retrieval path.
    It intentionally does not call the LLM.
    """
    original_query = str(query or "").strip()
    smart_query = normalize_query(build_generic_retrieval_query(original_query))
    count = collection.count()
    sample = collection.get(limit=5, include=["metadatas"])

    embedding_query = expand_query(smart_query)
    query_embedding = encode_query(embedding_query)
    raw = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(int(top_k or 10), 10),
        include=["documents", "metadatas", "distances"],
    )

    raw_docs = raw.get("documents", [[]])[0]
    raw_metas = raw.get("metadatas", [[]])[0]
    raw_dists = raw.get("distances", [[]])[0]

    where_filter = build_filter(False, None, None, None, None)
    keyword_docs, keyword_metas, keyword_dists = keyword_retrieve_chunks(
        query=smart_query,
        where_filter=where_filter,
        limit=max(int(top_k or 10), 10),
        use_personal_docs=False,
    )
    vector_docs, vector_metas, vector_dists = vector_retrieve_chunks(
        query=smart_query,
        top_k=max(int(top_k or 10), 10),
        where_filter=where_filter,
        use_personal_docs=False,
    )
    merged = list(zip(keyword_docs, keyword_metas, keyword_dists)) + list(zip(vector_docs, vector_metas, vector_dists))
    seen: set[str] = set()
    merged_docs: list[str] = []
    merged_metas: list[dict] = []
    merged_dists: list[float] = []
    for doc, meta, dist in merged:
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        merged_docs.append(doc)
        merged_metas.append(meta or {})
        merged_dists.append(dist)

    reranked_docs, reranked_metas, reranked_dists = rerank_results(
        smart_query,
        merged_docs,
        merged_metas,
        merged_dists,
        max(int(top_k or 10), 10),
    )
    docs, metas, dists = retrieve_chunks(
        query=smart_query,
        top_k=top_k,
        where_filter=where_filter,
        use_personal_docs=False,
    )
    context, sources = build_context(smart_query, docs, metas, dists)

    def item(doc: str, meta: dict | None, dist: float | None) -> dict[str, Any]:
        meta = meta or {}
        snippet = clean_text(str(doc or ""))[:700]
        # One-line explanation: Convert distance to float only if it is not None.
        distance = float(dist) if dist is not None else None
        return {
            "snippet": snippet,
            "metadata": meta,
            "distance": distance,
            "allowed": metadata_allows_query(meta),
            "keyword_score": keyword_score(smart_query, doc),
            "admission_evidence": admission_evidence_score(smart_query, doc),
            "role_evidence": role_evidence_score(smart_query, doc),
            "document_evidence": document_evidence_score(smart_query, doc),
            "fee_evidence": fee_evidence_score(smart_query, doc),
            "hostel_evidence": hostel_evidence_score(smart_query, doc),
            "drop_hint": (
                "table_of_contents"
                if is_toc_candidate(doc, meta) and "contents" not in normalize_text(smart_query)
                else "low_distance_and_no_lexical_evidence"
                # One-line explanation: Verify distance is not None before comparing to MAX_DISTANCE.
                if distance is not None and distance > MAX_DISTANCE and keyword_score(smart_query, doc) <= 0
                else ""
            ),
        }

    return {
        "original_query": original_query,
        "smart_retrieval_query": smart_query,
        "expanded_query": embedding_query,
        "intent": classify_admission_query(original_query),
        "collection_count": count,
        "sample_metadatas": sample.get("metadatas", []),
        "raw_results": [
            item(doc, meta, dist)
            for doc, meta, dist in zip(raw_docs, raw_metas, raw_dists)
        ],
        "keyword_results": [
            item(doc, meta, dist)
            for doc, meta, dist in zip(keyword_docs, keyword_metas, keyword_dists)
        ],
        "reranked_results": [
            item(doc, meta, dist)
            for doc, meta, dist in zip(reranked_docs, reranked_metas, reranked_dists)
        ],
        "final_results": [
            item(doc, meta, dist)
            for doc, meta, dist in zip(docs, metas, dists)
        ],
        "context_length": len(context),
        "source_previews": [
            {
                "file": source.get("file"),
                "page": source.get("page_label") or source.get("page"),
                "section": source.get("section_title"),
                "preview": clean_text(str(source.get("text") or ""))[:300],
            }
            for source in sources
        ],
    }


def _debug_preview(document: str, limit: int = 260) -> str:
    return clean_text(content_without_context_header(str(document or "")))[:limit]


def _debug_candidate_score(query: str, document: str, meta: dict | None, dist: float | None = None) -> float:
    try:
        # One-line explanation: Convert distance to float only if it is not None.
        distance = float(dist) if dist is not None else 999.0
    except Exception:
        distance = 999.0
    vector_score = max(0.0, 2.0 - distance) * 20.0
    return (
        keyword_score(query, document)
        + metadata_boost_score(query, document, meta or {})
        + admission_evidence_score(query, document)
        + document_evidence_score(query, document)
        + role_evidence_score(query, document)
        + fee_evidence_score(query, document)
        + hostel_evidence_score(query, document)
        + vector_score
    )


def _debug_candidate_item(
    query: str,
    document: str,
    meta: dict | None,
    dist: float | None = None,
    include_distance: bool = False,
) -> dict[str, Any]:
    meta = meta or {}
    item: dict[str, Any] = {
        "file": meta.get("filename") or meta.get("source_filename") or "Unknown document",
        "page": meta.get("page_label") or meta.get("page") or "?",
        "section": meta.get("section_title") or "general",
        "preview": _debug_preview(document),
    }
    if include_distance:
        try:
            item["distance"] = float(dist)
        except Exception:
            item["distance"] = None
    else:
        item["score"] = round(_debug_candidate_score(query, document, meta, dist), 2)
    return item


# TODO: split
def debug_rag_pipeline(query: str, top_k: int = 8) -> dict[str, Any]:
    """
    Structured RAG probe for debugging retrieval without calling the LLM.
    It uses the same official-document retrieval path as ask().
    """
    original_query = str(query or "").strip()
    normalized_query = normalize_query(original_query)
    smart_query = normalize_query(build_smart_retrieval_query(original_query))
    target_top_k = int(top_k or DEFAULT_TOP_K)
    where_filter = build_filter(False, None, None, None, None)

    try:
        collection_count = int(collection.count())
    except Exception:
        collection_count = 0

    keyword_docs, keyword_metas, keyword_dists = keyword_retrieve_chunks(
        query=smart_query,
        where_filter=where_filter,
        limit=150,
        use_personal_docs=False,
    )
    vector_docs, vector_metas, vector_dists = vector_retrieve_chunks(
        query=smart_query,
        top_k=100,
        where_filter=where_filter,
        use_personal_docs=False,
    )
    special_docs, special_metas, special_dists = special_list_keyword_retrieve(
        query=smart_query,
        where_filter=where_filter,
        use_personal_docs=False,
        limit=60,
    )

    combined = (
        list(zip(special_docs, special_metas, special_dists))
        + list(zip(keyword_docs, keyword_metas, keyword_dists))
        + list(zip(vector_docs, vector_metas, vector_dists))
    )
    merged_docs: list[str] = []
    merged_metas: list[dict] = []
    merged_dists: list[float] = []
    seen: set[str] = set()
    for doc, meta, dist in combined:
        key = candidate_dedupe_key(doc, meta)
        if key in seen:
            continue
        seen.add(key)
        merged_docs.append(doc)
        merged_metas.append(meta or {})
        merged_dists.append(dist)

    reranked_docs, reranked_metas, reranked_dists = rerank_results(
        smart_query,
        merged_docs,
        merged_metas,
        merged_dists,
        max(30, target_top_k * 4),
    )

    final_docs, final_metas, final_dists = retrieve_chunks(
        query=smart_query,
        top_k=target_top_k,
        where_filter=where_filter,
        use_personal_docs=False,
    )
    context, sources = build_context(smart_query, final_docs, final_metas, final_dists)

    return {
        "original_query": original_query,
        "normalized_query": normalized_query,
        "smart_retrieval_query": smart_query,
        "collection_count": collection_count,
        "keyword_candidates": [
            _debug_candidate_item(smart_query, doc, meta, dist)
            for doc, meta, dist in zip(keyword_docs[:target_top_k], keyword_metas[:target_top_k], keyword_dists[:target_top_k])
        ],
        "vector_candidates": [
            _debug_candidate_item(smart_query, doc, meta, dist, include_distance=True)
            for doc, meta, dist in zip(vector_docs[:target_top_k], vector_metas[:target_top_k], vector_dists[:target_top_k])
        ],
        "merged_candidates_count": len(merged_docs),
        "reranked_candidates": [
            _debug_candidate_item(smart_query, doc, meta, dist)
            for doc, meta, dist in zip(reranked_docs[:target_top_k], reranked_metas[:target_top_k], reranked_dists[:target_top_k])
        ],
        "final_selected_chunks": [
            _debug_candidate_item(smart_query, doc, meta, dist, include_distance=True)
            | {"score": round(_debug_candidate_score(smart_query, doc, meta, dist), 2)}
            for doc, meta, dist in zip(final_docs, final_metas, final_dists)
        ],
        "final_context_length": len(context),
        "sources_count": len(sources),
    }





def debug_person_lookup_blocked(query: str, context: str) -> None:
    if not DEBUG_RAG:
        return
    print("[PERSON_LOOKUP_BLOCKED] No clear person name found near requested title.")
    print("Requested title:", get_requested_person_title(query))
    print("Final context preview:", (context or "")[:1000])
