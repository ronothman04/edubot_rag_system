import re
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from db import collection


SEARCH_TERMS = [
    "website committee",
    "computer science",
    "departments",
    "email",
    "contact",
]


def norm(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("commitee", "committee")
    value = value.replace("committe", "committee")
    value = value.replace("comittee", "committee")
    value = re.sub(r"[^a-z0-9\s@._-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def preview(value: str, limit: int = 500) -> str:
    return " ".join((value or "").split())[:limit]


def print_match(term: str, doc: str, meta: dict) -> None:
    print(
        "file=", meta.get("filename"),
        "page=", meta.get("page"),
        "scope=", meta.get("scope"),
        "status=", meta.get("status"),
        "deleted=", meta.get("deleted"),
        "chunk_index=", meta.get("chunk_index"),
    )
    print("preview=", preview(doc))


def main() -> None:
    result = collection.get(include=["documents", "metadatas"])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    print("Total chunks:", len(docs))

    for term in SEARCH_TERMS:
        print(f"\n=== Search: {term!r} ===")
        term_norm = norm(term)
        count = 0

        for doc, meta in zip(docs, metas):
            if term_norm in norm(doc):
                count += 1
                print(f"\nMatch {count}:")
                print_match(term, doc, meta or {})

                if count >= 10:
                    break

        print("Matches shown:", count)


if __name__ == "__main__":
    main()
