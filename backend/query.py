from db import collection

data = collection.get()

ids = data.get("ids", [])
docs = data.get("documents", [])
metas = data.get("metadatas", [])

# ---- RAW VIEW ----
print("\nALL DATA:")
for i, d in zip(ids, docs):
    print(f"{i} -> {d}")

# ---- ACTIVE DATA ONLY ----
print("\nACTIVE DATA ONLY:")
for i, d, m in zip(ids, docs, metas):
    if m and m.get("deleted", False):
        continue
    print(i, "->", d)

# ---- SEMANTIC SEARCH ----
results = collection.query(
    query_texts=["vehicles with the most efficient transportation"],
    n_results=3,
    where={"deleted": False}
)

print("\nQUERY RESULTS:")

if results["documents"]:
    for i, doc in enumerate(results["documents"][0]):
        print(f"{i+1}. {doc}")
else:
    print("No results found")