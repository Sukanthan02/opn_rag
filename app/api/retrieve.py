from fastapi import APIRouter
from app.services.retrieval_service import retrieve_top_chunks
from app.schemas import RetrievalPoint

router = APIRouter(tags=["Search"])

@router.get(
    "/retrieve",
    response_model=list[RetrievalPoint],
    summary="Search for similar agents",
    description="Find most relevant agents/subagents using semantic similarity"
)
def retrieve(query: str, top_k: int = 3):
    """
    Retrieve the most semantically similar agents/subagents for a given query.
    
    Uses vector similarity search in Qdrant database with Nomic embeddings.
    
    **Query Parameters:**
    - `query` (required): User query to search for relevant agents
    - `top_k` (optional): Number of top results to return (default: 3, max: 10)
    
    **Returns:** List of agents/subagents sorted by similarity score (0.0-1.0)
    
    Each result includes:
    - `score`: Cosine similarity score
    - `payload`: Agent/subagent metadata (type, name, description, id)
    """
    chunks = retrieve_top_chunks(query, top_k)
    return [
        RetrievalPoint(score=c["score"], payload=c["payload"])
        for c in chunks
    ]
