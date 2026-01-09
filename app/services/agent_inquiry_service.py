from app.db.mysql import SessionLocal
from app.models.agent import Agent
from app.models.subagent import SubAgent
from app.logger import logger
from app.services.llm_service import grok_call


def is_agent_inquiry(query: str) -> bool:
    """
    Detect if user query is asking ABOUT available agents/subagents or their capabilities.
    Uses semantic LLM classification to distinguish:
    - INQUIRY: "what agents exist?", "what can agent X do?", "does agent create ppt?"
    - SERVICE: "i want to use agent X", "send me to agent", "route to email agent"
    """
    prompt = f"""You are an expert query classifier. Classify whether the user is asking FOR INFORMATION ABOUT agents, or asking TO USE/ACCESS an agent's service.

User Query: "{query}"

CLASSIFICATION RULES:

=== Answer "YES" (Agent Information Inquiry) ONLY if ===
- User asks WHAT agents exist or are available
- User asks WHAT agent can do / capabilities
- User asks ABOUT agent features without wanting to use it yet
- Examples: "list agents", "what agents do you have?", "can document agent create ppt?", "does email agent handle gmail?"

=== Answer "NO" (Service Request / Routing) ONLY if ===
- User wants to USE / ACCESS an agent ("i want to use email agent", "send me to agent X")
- User asks to ROUTE / REDIRECT to an agent ("route to email agent", "take me to document agent")
- User is REQUESTING a service (even if it mentions an agent name)
- User is ASKING FOR ACTION, not asking about capability
- Examples: "I want to send emails", "use email agent", "route to email", "take me to document agent"

KEY DISTINCTION - These are DIFFERENT:
- "can email agent send emails?" → YES (asking about capability)
- "I want to send emails" → NO (asking to use service)
- "does document agent create ppt?" → YES (asking about capability)  
- "create a ppt for me" → NO (asking for service)
- "what is email agent?" → YES (asking about agent)
- "I want to use email agent" → NO (asking to access/use)
- "route to email agent" → NO (asking for routing)

Respond with ONLY "yes" or "no" - nothing else:
Answer:"""
    
    try:
        response = grok_call(
            prompt=prompt,
            max_tokens=5,
            temperature=0.0
        )
        result = response.strip().lower()
        logger.debug(f"[AGENT INQUIRY] Query: '{query}' → Result: {result}")
        return result.startswith("yes")
    
    except Exception as e:
        logger.exception(f"Error in is_agent_inquiry: {e}")
        return False


def get_all_agents_with_subagents() -> dict:
    """
    Fetch all agents and their subagents from MySQL with full details.
    Returns a structured dict for LLM processing.
    """
    db = SessionLocal()
    
    try:
        agents_data = []
        agents = db.query(Agent).all()
        
        for agent in agents:
            subagents = db.query(SubAgent).filter(SubAgent.agent_id == agent.id).all()
            
            agent_info = {
                "name": agent.name,
                "description": agent.description,
                "capabilities": agent.capabilities or [],
                "subagents": [
                    {
                        "name": sub.name,
                        "description": sub.description,
                        "capabilities": sub.capabilities or []
                    }
                    for sub in subagents
                ]
            }
            agents_data.append(agent_info)
        
        logger.info(f"Retrieved {len(agents_data)} agents with subagents")
        return {
            "agents": agents_data,
            "total_agents": len(agents_data)
        }
    
    except Exception as e:
        logger.exception("Failed to fetch agents and subagents")
        raise e
    
    finally:
        db.close()
