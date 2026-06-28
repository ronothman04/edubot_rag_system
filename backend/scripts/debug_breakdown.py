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
)

query = "i want to apply for computer science, what are the courses available in it?"

res = collection.get(
    where={
        "$and": [
            {"filename": {"$eq": "Handbook_2023-24.pdf"}},
            {"page": {"$eq": 17}}
        ]
    },
    include=["documents", "metadatas"]
)
doc = res["documents"][0]
meta = res["metadatas"][0]

print(f"Doc preview: {doc[:150]}...")
print(f"Meta: {meta}")

lexical_score = keyword_score(query, doc)
admission_ev = admission_evidence_score(query, doc)
doc_ev = document_evidence_score(query, doc)
role_ev = role_evidence_score(query, doc)
fee_ev = fee_evidence_score(query, doc)
hostel_ev = hostel_evidence_score(query, doc)
meta_boost = metadata_boost_score(query, doc, meta)
hostel_rel = hostel_relevance_score(query, doc, meta)
proc_rel = procedural_relevance_score(query, doc, meta)
person_lookup_rel = person_lookup_relevance_score(query, doc, meta)
staff_rel = staff_relevance_score(query, doc, meta)

print("\n--- COMPONENT SCORES ---")
print(f"lexical_score (keyword_score): {lexical_score}")
print(f"admission_evidence_score: {admission_ev}")
print(f"document_evidence_score: {doc_ev}")
print(f"role_evidence_score: {role_ev}")
print(f"fee_evidence_score: {fee_ev}")
print(f"hostel_evidence_score: {hostel_ev}")
print(f"metadata_boost_score: {meta_boost}")
print(f"hostel_relevance_score: {hostel_rel}")
print(f"procedural_relevance_score: {proc_rel}")
print(f"person_lookup_relevance_score: {person_lookup_rel}")
print(f"staff_relevance_score: {staff_rel}")

evidence_score = (
    admission_ev
    + doc_ev
    + role_ev
    + fee_ev
    + hostel_ev
    + meta_boost
    + hostel_rel * 120.0
    + proc_rel * 90.0
    + person_lookup_rel * 140.0
)
print(f"\nCalculated evidence_score: {evidence_score}")
print(f"Calculated Total (lexical_score + evidence_score): {lexical_score + evidence_score}")
