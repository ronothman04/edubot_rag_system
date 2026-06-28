import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from db import collection

print("Collection count:", collection.count())

result = collection.get(
    include=["documents", "metadatas"],
    limit=10000,
)

docs = result.get("documents", [])
metas = result.get("metadatas", [])

matches = []

for doc, meta in zip(docs, metas):
    text = str(doc or "").lower()
    if "principal" in text or "college authorities" in text or "administration" in text:
        matches.append((doc, meta))

print("Principal-related chunks found:", len(matches))

for i, (doc, meta) in enumerate(matches[:10], start=1):
    print("\n--- MATCH", i, "---")
    print("META:", meta)
    print("TEXT:", str(doc)[:1500])