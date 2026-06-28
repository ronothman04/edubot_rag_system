import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from db import collection

SEARCH_WORDS = [
    "hod",
    "head of department",
    "department of economics",
    "department of english",
    "department of political science",
    "department of commerce",
    "economics",
    "english",
    "political science",
    "commerce",
    "charlene",
    "swer",
]

result = collection.get(
    include=["documents", "metadatas"]
)

docs = result.get("documents", [])
metas = result.get("metadatas", [])

print("Total chunks in ChromaDB:", len(docs))

found_count = 0

for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
    text = doc or ""
    lower = text.lower()

    if any(word in lower for word in SEARCH_WORDS):
        found_count += 1

        print("\n" + "=" * 80)
        print("CHUNK:", i)
        print("File:", meta.get("filename"))
        print("Page:", meta.get("page"))
        print("Scope:", meta.get("scope"))
        print("Department:", meta.get("department"))
        print("Document type:", meta.get("document_type"))
        print("-" * 80)
        print(text[:2500])

print("\nMatched chunks:", found_count)