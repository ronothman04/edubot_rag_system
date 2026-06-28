import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from db import collection
from rag.scoring import keyword_score, metadata_boost_score, staff_relevance_score, role_evidence_score

query = "i want to apply for computer science, what are the courses available in it?"

# Let's inspect the high scoring items:
# 1. Prospectus2026.pdf Page 22 (POST GRADUATE COURSES)
# 2. Prospectus2026.pdf Page 20 (Admission PROCEDURE)
# 3. Prospectus2026.pdf Page 17 (FEES STRUCTURE)
# 4. Handbook_2023-24.pdf Page 17 (Dept of Chemistry)

items_to_check = [
    ("Prospectus2026.pdf", 22),
    ("Prospectus2026.pdf", 20),
    ("Prospectus2026.pdf", 17),
    ("Handbook_2023-24.pdf", 17),
]

for filename, page in items_to_check:
    res = collection.get(
        where={
            "$and": [
                {"filename": {"$eq": filename}},
                {"page": {"$eq": page}}
            ]
        },
        include=["documents", "metadatas"]
    )
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])
    
    for doc, meta in zip(docs, metas):
        print(f"--- {filename} Page {page} ---")
        print(f"Section: {meta.get('section_title')}")
        print(f"Preview: {doc[:150]}...")
        
        lex = keyword_score(query, doc)
        meta_b = metadata_boost_score(query, doc, meta)
        staff_b = staff_relevance_score(query, doc, meta)
        role_b = role_evidence_score(query, doc)
        
        print(f"keyword_score: {lex}")
        print(f"metadata_boost_score: {meta_b}")
        print(f"staff_relevance_score: {staff_b}")
        print(f"role_evidence_score: {role_b}")
        print(f"Total: {lex + meta_b + staff_b + role_b}\n")
