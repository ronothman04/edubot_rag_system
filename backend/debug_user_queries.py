import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.main import ask

print("--- QUERY: who is the faculty of BBA ---")
res1 = ask("who is the faculty of BBA")
print("Response type:", res1.get("response_type"))
print("Answer:")
print(res1.get("answer"))

print("\n--- QUERY: how many departments are there? ---")
res2 = ask("how many departments are there?")
print("Response type:", res2.get("response_type"))
print("Answer:")
print(res2.get("answer"))
