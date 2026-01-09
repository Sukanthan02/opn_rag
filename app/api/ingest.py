from fastapi import APIRouter
from app.services.ingest_service import ingest_agent, ingest_subagent
from app.schemas import AgentRequest, AgentResponse, SubAgentRequest, SubAgentResponse

router = APIRouter(tags=["Ingest"])

@router.post(
    "/agent",
    response_model=AgentResponse,
    summary="Create a new agent",
    description="Ingest a new agent with name, description, and optional list of capabilities"
)
def add_agent(request: AgentRequest):
    """
    Create and ingest a new agent to the system.
    
    The agent will be:
    - Stored in MySQL with metadata and capabilities
    - Embedded and indexed in Qdrant vector database
    - Available for routing and inquiry
    
    **Request Body:**
    - `name`: Unique name of the agent
    - `description`: What the agent does
    - `capabilities`: Optional list of capability strings (e.g., ["orchestration", "validation"])
    
    **Returns:** Agent ID of the created agent
    """
    return {"agent_id": ingest_agent(request.name, request.description, request.capabilities)}


@router.post(
    "/subagent",
    response_model=SubAgentResponse,
    summary="Create a subagent under an agent",
    description="Ingest a new subagent under an existing agent"
)
def add_subagent(request: SubAgentRequest):
    """
    Create and ingest a new subagent under an existing agent.
    
    The subagent will be:
    - Stored in MySQL linked to parent agent
    - Embedded and indexed in Qdrant vector database
    - Available for routing and inquiry
    
    **Request Body:**
    - `agent_id`: Parent agent ID (must exist)
    - `name`: Unique name of the subagent
    - `description`: What the subagent does
    - `capabilities`: Optional list of capability strings
    
    **Returns:** Status confirmation
    """
    ingest_subagent(request.agent_id, request.name, request.description, request.capabilities)
    return {"status": "ok"}
