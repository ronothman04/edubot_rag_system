from sentence_transformers import SentenceTransformer


def get_embedding_model():
    """
    Get the sentence transformer model for generating embeddings.
    Uses the all-MiniLM-L6-v2 model for efficient and effective embeddings.
    """
    return SentenceTransformer("all-MiniLM-L6-v2")
