import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.retrieval import retrieve_chunks

query = "i want to apply for computer science, what are the courses available in it?"
print(f"QUERY: {query}\n")

# Run retrieve_chunks to print the debug statements inside it
docs, metas, dists = retrieve_chunks(query, 5, None)
