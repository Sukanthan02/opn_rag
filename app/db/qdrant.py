from qdrant_client import QdrantClient
from app.config import QDRANT_PATH, QDRANT_COLLECTION, VECTOR_SIZE
from app.logger import logger

_qdrant_client = None

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        logger.info("Initializing Qdrant Local Client")
        _qdrant_client = QdrantClient(path=QDRANT_PATH)
    return _qdrant_client

def init_qdrant():
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]

    if QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "size": VECTOR_SIZE,
                "distance": "Cosine"
            }
        )
        logger.info("Qdrant collection created")
