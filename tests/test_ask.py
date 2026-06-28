import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from rag import ask

queries = [
    "can i apply for Botany",
    "can i apply for BCA",
]

for q in queries:
    res = ask(q, top_k=5)
    print(f"\\nQuery: {q}")
    print(f"Answer: {res['answer']}")
