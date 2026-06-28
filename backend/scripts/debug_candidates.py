import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from db import collection
from rag.scoring import (
    keyword_score,
    metadata_boost_score,
    admission_evidence_score,
    document_evidence_score,
    role_evidence_score,
    fee_evidence_score,
    hostel_evidence_score,
    hostel_relevance_score,
    procedural_relevance_score,
    person_lookup_relevance_score,
    staff_relevance_score,
    score_chunk_by_intent,
)
from rag.retrieval import keyword_retrieve_chunks, vector_retrieve_chunks, special_list_keyword_retrieve

query = "i want to apply for computer science, what are the courses available in it?"

# Let's get the candidates like retrieve_chunks does:
keyword_docs, keyword_metas, keyword_dists = keyword_retrieve_chunks(query, None, 150)
vector_docs, vector_metas, vector_dists = vector_retrieve_chunks(query, 100, None)
fallback_docs, fallback_metas, fallback_dists = special_list_keyword_retrieve(query, None, False, 60)

combined = (
    list(zip(fallback_docs, fallback_metas, fallback_dists))
    + list(zip(keyword_docs, keyword_metas, keyword_dists))
    + list(zip(vector_docs, vector_metas, vector_dists))
)

seen = set()
unique_candidates = []
for doc, meta, dist in combined:
    meta = meta or {}
    key = (doc, meta.get("filename", ""), meta.get("page", ""))
    if key in seen:
        continue
    seen.add(key)
    unique_candidates.append((doc, meta, dist))

print(f"Total unique candidates: {len(unique_candidates)}")

# Score all of them
scored_candidates = []
for doc, meta, dist in unique_candidates:
    lexical = keyword_score(query, doc)
    vector_s = max(0.0, 2.0 - dist) * 20.0
    meta_s = metadata_boost_score(query, doc, meta)
    
    evidence_s = (
        admission_evidence_score(query, doc)
        + document_evidence_score(query, doc)
        + role_evidence_score(query, doc)
        + fee_evidence_score(query, doc)
        + hostel_evidence_score(query, doc)
        + hostel_relevance_score(query, doc, meta) * 120.0
        + procedural_relevance_score(query, doc, meta) * 90.0
        + person_lookup_relevance_score(query, doc, meta) * 140.0
        + staff_relevance_score(query, doc, meta)
    )
    
    intent_s = score_chunk_by_intent(query, doc, meta)
    
    final_score = lexical + vector_s + meta_s + evidence_s + intent_s
    
    scored_candidates.append((final_score, doc, meta, dist, lexical, vector_s, meta_s, evidence_s, intent_s))

scored_candidates.sort(key=lambda x: x[0], reverse=True)

# Print the top 10
print("\n--- TOP 10 RERANKED RESULTS ---")
for i, (final, doc, meta, dist, lex, vec, metas, ev, intent) in enumerate(scored_candidates[:10], start=1):
    print(f"[{i}] {meta.get('filename')} Page {meta.get('page')} (Total: {final:.2f})")
    print(f"   Section: {meta.get('section_title')}")
    print(f"   Breakdown: lex={lex:.1f}, vec={vec:.1f}, meta={metas:.1f}, ev={ev:.1f}, intent={intent:.1f}")
    print(f"   Preview: {' '.join(doc.split())[:180]}...\n")
