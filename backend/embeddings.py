import os

from sentence_transformers import SentenceTransformer


# Keep this model consistent between ingestion and retrieval.
# If EMBEDDING_MODEL changes after documents are already stored in ChromaDB,
# clear/recreate the collection and re-ingest every document.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MODEL_LOCAL_FILES_ONLY = (
    os.getenv("MODEL_LOCAL_FILES_ONLY", "true").strip().lower() == "true"
)

_model = None
_model_load_failed = False


def get_embedding_model() -> SentenceTransformer:
    global _model, _model_load_failed

    if _model_load_failed:
        raise RuntimeError(
            f"Embedding model {EMBEDDING_MODEL!r} is not available locally."
        )

    if _model is None:
        try:
            import torch
            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            
            print(f"[EduBot] Loading embedding model on device: cpu")
            _model = SentenceTransformer(
                EMBEDDING_MODEL,
                device="cpu",
                local_files_only=MODEL_LOCAL_FILES_ONLY,
            )
        except Exception:
            _model_load_failed = True
            raise

    return _model


def prefix_query_for_search(query: str) -> str:
    """Return the BGE-style query text used for semantic search."""
    query = str(query or "").strip()
    return f"{QUERY_PREFIX}{query}" if query else QUERY_PREFIX.strip()


def encode_texts(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Encode passage texts with the shared cached embedding model."""
    if not texts:
        return []

    model = get_embedding_model()
    kwargs = {
        "show_progress_bar": False,
        "batch_size": batch_size,
    }

    try:
        embeddings = model.encode(texts, normalize_embeddings=True, **kwargs)
    except TypeError:
        embeddings = model.encode(texts, **kwargs)

    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()

    return embeddings


def encode_query(query: str) -> list[float]:
    """Encode a search query using the shared cached embedding model."""
    if not str(query or "").strip():
        return []

    model = get_embedding_model()
    query_text = prefix_query_for_search(query)

    try:
        embedding = model.encode(query_text, normalize_embeddings=True)
    except TypeError:
        embedding = model.encode(query_text)

    if hasattr(embedding, "tolist"):
        return embedding.tolist()

    return embedding
