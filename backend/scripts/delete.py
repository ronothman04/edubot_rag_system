import chromadb
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from db import collection
collection.update(
    ids=["chunk_0"],
    metadatas=[{"deleted": True}]
)
print("chunk_0 soft deleted")