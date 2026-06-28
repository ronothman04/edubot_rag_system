import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from rag import build_smart_retrieval_query, normalize_query, extract_personal_eligibility_case, build_filter
from embeddings import encode_query
from db import collection
from rag import keyword_retrieve_chunks, vector_retrieve_chunks

q = "can i apply for Botany"
smart_query = build_smart_retrieval_query(q)
where_filter = build_filter(False, None, None, None, None)

keyword_docs, _, _ = keyword_retrieve_chunks(smart_query, where_filter, limit=150, use_personal_docs=False)
vector_docs, _, _ = vector_retrieve_chunks(encode_query(smart_query), 150, where_filter, False)
docs = keyword_docs + vector_docs

case = extract_personal_eligibility_case(q)
t_lower = normalize_query("Botany")
keywords = ["eligibility", "eligible", "marks", "qualifying", "subject combination", "minimum marks", "passed", "percentage", "admission criteria", "required subject"]

for i, doc in enumerate(docs):
    d_lower = normalize_query(doc)
    if t_lower in d_lower:
        found_kw = [kw for kw in keywords if kw in d_lower]
        if found_kw:
            print(f"Chunk {i} matches Botany AND keywords: {found_kw}")
            print(doc[:300])
            print("-" * 50)
