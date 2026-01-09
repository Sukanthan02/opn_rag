from app.embeddings.nomic_local import get_embedding
from app.db.qdrant import get_qdrant_client
from app.config import QDRANT_COLLECTION


def retrieve_top_chunks(query: str, top_k: int = 3):
    embedding = get_embedding(query)

    client = get_qdrant_client()

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=embedding,
        limit=top_k,
        with_payload=True
    )

    return [
        {
            "score": point.score,
            "payload": point.payload
        }
        for point in results.points
    ]




