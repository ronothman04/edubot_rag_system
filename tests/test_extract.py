import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from rag import extract_target_course_from_query, build_smart_eligibility_retrieval_query, build_smart_retrieval_query

queries = [
    "can i apply for Botany",
    "can i apply for BCA",
    "can i apply for Zoology",
    "what are the eligibility criteria for Botany",
    "what courses are available for admission"
]

for q in queries:
    target = extract_target_course_from_query(q)
    eligibility_query = build_smart_eligibility_retrieval_query(q)
    smart_query = build_smart_retrieval_query(q)
    print(f"Query: {q}")
    print(f"Target Course: {target}")
    print(f"Smart Query: {smart_query}\\n")
