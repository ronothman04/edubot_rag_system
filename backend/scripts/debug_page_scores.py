import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from db import collection
from rag.scoring import keyword_score, metadata_boost_score, staff_relevance_score, role_evidence_score
from rag.retrieval import rerank_results

query = "i want to apply for computer science, what are the courses available in it?"
print(f"QUERY: {query}\n")

# Get all chunks from Prospectus2026.pdf
res = collection.get(where={"filename": {"$eq": "Prospectus2026.pdf"}}, include=["documents", "metadatas"])
docs = res.get("documents", [])
metas = res.get("metadatas", [])

for doc, meta in zip(docs, metas):
    page = meta.get("page")
    if page in [8, 9, 10, 21]:
        print(f"--- Prospectus2026.pdf Page {page} ---")
        print(f"Section: {meta.get('section_title')}")
        print(f"Preview: {doc[:200]}...")
        
        lex = keyword_score(query, doc)
        meta_b = metadata_boost_score(query, doc, meta)
        staff_b = staff_relevance_score(query, doc, meta)
        role_b = role_evidence_score(query, doc)
        
        print(f"keyword_score: {lex}")
        print(f"metadata_boost_score: {meta_b}")
        print(f"staff_relevance_score: {staff_b}")
        print(f"role_evidence_score: {role_b}")
        print(f"Total: {lex + meta_b + staff_b + role_b}\n")
