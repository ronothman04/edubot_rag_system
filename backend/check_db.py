from db import collection, collection_stats


def preview(value: str, limit: int = 700) -> str:
    value = " ".join((value or "").split())
    return value[:limit]


def main() -> None:
    stats = collection_stats()
    print("Collection stats:")
    for key, value in stats.items():
        print(f"{key}: {value}")

    result = collection.get(include=["documents", "metadatas"], limit=5)
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    print("\nSample chunks:")
    for index, (doc, meta) in enumerate(zip(docs, metas), start=1):
        print(f"\n[{index}] metadata: {meta}")
        print(f"[{index}] text: {preview(doc)}")


if __name__ == "__main__":
    main()
