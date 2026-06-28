import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from rag import ask


QUESTIONS = [
    "Who are the members of the Examination Committee?",
    "What are the rules and guidelines for Stephen Hall hostel?",
    "How do I contact the college admission office?",
]


def main() -> None:
    for question in QUESTIONS:
        print(f"\n=== {question} ===")
        result = ask(question)
        print("answer:")
        print(result.get("answer"))
        print("\nsources:")
        for source in result.get("sources", []):
            # One-line explanation: Print all distance and score metrics for debugging retrieval.
            print(
                "file=", source.get("file"),
                "page=", source.get("page"),
                "distance=", source.get("distance"),
                "vector_distance=", source.get("vector_distance"),
                "rerank_score=", source.get("rerank_score"),
                "keyword_score=", source.get("keyword_score"),
            )


if __name__ == "__main__":
    main()
