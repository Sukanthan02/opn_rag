from sentence_transformers import SentenceTransformer

# Official Nomic local embedding model
_model = SentenceTransformer(
    "nomic-ai/nomic-embed-text-v1",
    trust_remote_code=True
)

def get_embedding(text: str):

    return _model.encode(text, normalize_embeddings=True).tolist()
