import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.main import ask

query = "i want to apply for computer science, what are the courses available in it?"
print(f"QUERY: {query}")
result = ask(query)
print("\n--- ANSWER ---")
print(result.get("answer"))
print("\n--- SOURCES ---")
for source in result.get("sources", []):
    print(
        f"file={source.get('file')} page={source.get('page')} score={source.get('keyword_score')} dist={source.get('distance')}"
    )
    print(f"section: {source.get('section_title')}")
    print(f"text preview: {source.get('text')[:300]}\n")
