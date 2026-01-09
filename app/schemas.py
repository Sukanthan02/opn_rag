from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


# =====================
# INGEST SCHEMAS
# =====================
class AgentRequest(BaseModel):
    """Request schema for creating an agent"""
    name: str
    description: str
    capabilities: Optional[List[str]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Open Negotiation AI Agent",
                "description": "Parent orchestration agent responsible for managing, controlling, and validating the complete workflow",
                "capabilities": [
                    "master orchestration",
                    "workflow control",
                    "sequential execution",
                    "prerequisite validation"
                ]
            }
        }


class AgentResponse(BaseModel):
    """Response schema for agent creation"""
    agent_id: int
    
    class Config:
        json_schema_extra = {
            "example": {"agent_id": 1}
        }


class SubAgentRequest(BaseModel):
    """Request schema for creating a subagent"""
    agent_id: int
    name: str
    description: str
    capabilities: Optional[List[str]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": 1,
                "name": "Negotiation Validator",
                "description": "Validates negotiation prerequisites and conditions",
                "capabilities": [
                    "prerequisite validation",
                    "conditional checking",
                    "error isolation"
                ]
            }
        }


class SubAgentResponse(BaseModel):
    """Response schema for subagent creation"""
    status: str
    
    class Config:
        json_schema_extra = {
            "example": {"status": "ok"}
        }


# =====================
# RETRIEVAL SCHEMAS
# =====================
class RetrievalPayload(BaseModel):
    """Payload data from retrieved agent/subagent"""
    type: str
    agent_id: int
    subagent_id: Optional[int] = None
    name: str
    description: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "agent",
                "agent_id": 1,
                "subagent_id": None,
                "name": "Open Negotiation AI Agent",
                "description": "Parent orchestration agent"
            }
        }


class RetrievalPoint(BaseModel):
    """Single retrieved agent/subagent"""
    score: float
    payload: RetrievalPayload
    
    class Config:
        json_schema_extra = {
            "example": {
                "score": 0.95,
                "payload": {
                    "type": "agent",
                    "agent_id": 1,
                    "subagent_id": None,
                    "name": "Open Negotiation AI Agent",
                    "description": "Parent orchestration agent"
                }
            }
        }


# =====================
# CHAT SCHEMAS
# =====================
class RoutingResponse(BaseModel):
    """Response for agent routing query"""
    type: str = "routing"
    routing: str
    message: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "routing",
                "routing": '{"agent": "Open Negotiation AI Agent", "subagent": "Email Sending Agent"}',
                "message": "I understand you need to send an email. I'm routing you to the Email Sending Agent which specializes in email operations."
            }
        }


class SubAgentInfo(BaseModel):
    """SubAgent information with capabilities"""
    name: str
    description: str
    capabilities: Optional[List[str]] = None


class AgentInfo(BaseModel):
    """Agent information with subagents"""
    name: str
    description: str
    capabilities: Optional[List[str]] = None
    subagents: List[SubAgentInfo] = []


class ClarificationResponse(BaseModel):
    """Response for clarification question in conversation mode"""
    type: str = "clarification"
    response: str
    session_id: str
    clarification_count: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "clarification",
                "response": "What would you like to do with the files? (rename, validate, organize)\n\nSuggested agents: File Manager Agent, Document Validator",
                "session_id": "abc123",
                "clarification_count": 1
            }
        }


class AgentInquiryResponse(BaseModel):
    """Response for agent inquiry query"""
    type: str = "agent_inquiry"
    response: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "agent_inquiry",
                "response": "I have the following agents available: Open Negotiation AI Agent which handles orchestration, workflow control, and validation. This agent includes a Negotiation Validator subagent that can perform prerequisite validation and conditional checking."
            }
        }


class InvalidQueryResponse(BaseModel):
    """Response for invalid query that fails validation"""
    type: str = "invalid_query"
    response: str
    confidence: float
    suggested_action: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "invalid_query",
                "response": "I'm sorry, but I couldn't process your query. Query appears to be random text without clear meaning or intent.",
                "confidence": 0.15,
                "suggested_action": "reject"
            }
        }

