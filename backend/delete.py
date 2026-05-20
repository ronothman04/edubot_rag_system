import chromadb
from db import collection
collection.update(
    ids=["chunk_0"],
    metadatas=[{"deleted": True}]
)
print("chunk_0 soft deleted")