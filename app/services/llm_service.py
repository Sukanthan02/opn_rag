from groq import Groq
import json
from datetime import datetime

from app.config import (
    GROK_API_KEY,
    GROK_MODEL,
    CONVERSATION_MODE
)
from app.db.mysql import SessionLocal
from app.models.agent import Agent
from app.models.subagent import SubAgent
from app.logger import logger, llm_logger

# ============================
# GROK CLIENT (Native)
# ============================
_grok_client = Groq(
    api_key=GROK_API_KEY
)


def _get_agent_with_subagents(agent_id: int) -> dict:
    """
    Fetch agent and all its subagents from MySQL.
    Returns complete hierarchy with descriptions and capabilities.
    """
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return None
        
        subagents = db.query(SubAgent).filter(SubAgent.agent_id == agent_id).all()
        
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "capabilities": agent.capabilities or [],
            "subagents": [
                {
                    "id": sub.id,
                    "name": sub.name,
                    "description": sub.description,
                    "capabilities": sub.capabilities or []
                }
                for sub in subagents
            ]
        }
    finally:
        db.close()


def _enrich_routing_context(vector_chunks):
    """
    Take vector search results and enrich them with full agent hierarchy from MySQL.
    Returns a dict with matched agents and their complete subagent information.
    """
    enriched_agents = {}
    
    for chunk in vector_chunks:
        agent_id = chunk['payload'].get('agent_id')
        if not agent_id:
            continue
        
        # If we haven't fetched this agent yet, fetch it with all subagents
        if agent_id not in enriched_agents:
            agent_data = _get_agent_with_subagents(agent_id)
            if agent_data:
                enriched_agents[agent_id] = agent_data
    
    return enriched_agents


def route_agent(query, chunks):
    """
    Route user query to appropriate agent and subagent.
    Enriches vector search results with full MySQL data for intelligent routing.
    Returns JSON: {"agent": "agent_name", "subagent": "subagent_name or null"}
    """
    llm_logger.debug(f"[ROUTE AGENT] Starting routing for query: {query[:100]}...")
    
    # Enrich vector search results with complete agent hierarchy from MySQL
    enriched_agents = _enrich_routing_context(chunks)
    
    if not enriched_agents:
        llm_logger.warning(f"[ROUTE AGENT] No enriched agents found, returning null routing")
        return json.dumps({"agent": None, "subagent": None})
    
    llm_logger.debug(f"[ROUTE AGENT] Enriched {len(enriched_agents)} agents from MySQL")
    
    # Format enriched context for LLM
    context_lines = []
    for agent_id, agent_data in enriched_agents.items():
        context_lines.append(f"[AGENT] Name: {agent_data['name']}")
        context_lines.append(f"  Description: {agent_data['description']}")
        
        if agent_data.get('capabilities'):
            caps_str = " | ".join(agent_data['capabilities'])
            context_lines.append(f"  Capabilities: {caps_str}")
        
        if agent_data.get('subagents'):
            context_lines.append(f"  Subagents under {agent_data['name']}:")
            for subagent in agent_data['subagents']:
                context_lines.append(f"    [SUBAGENT] Name: {subagent['name']}")
                context_lines.append(f"      Description: {subagent['description']}")
                if subagent.get('capabilities'):
                    sub_caps = " | ".join(subagent['capabilities'])
                    context_lines.append(f"      Capabilities: {sub_caps}")
        
        context_lines.append("")
        context_lines.append("")
    
    context = "\n".join(context_lines)
    llm_logger.debug(f"[ROUTE AGENT] Context size: {len(context)} chars with {len(enriched_agents)} agents")

    prompt = f"""You are an intelligent routing engine. Analyze the user query and available agents to make the best routing decision.

User Query:
{query}

Available Agents and Subagents (with full details):
{context}

ROUTING ANALYSIS TASK:
1. Understand what the user is trying to do
2. Match the query intent to the most relevant agent
3. If the matched agent has subagents, determine if any subagent is more specific for this task
4. Return the best routing decision

DECISION RULES:
- Return the MAIN AGENT if no specific subagent match
- Return the SUBAGENT only if its description/capabilities directly match the query better than the main agent
- If no agent matches well, both can be null
- Always check agent descriptions and capabilities carefully

RESPONSE FORMAT:
Return ONLY valid JSON (no markdown, no code fence, no extra text):
{{
  "agent": "<agent_name or null>",
  "subagent": "<subagent_name or null>"
}}



Now analyze the user query and return ONLY the JSON response:
"""

    llm_logger.debug(f"[ROUTE AGENT] Using Grok for routing decision")
    result = grok_call(prompt, max_tokens=512, temperature=0.0)
    
    llm_logger.debug(f"[ROUTE AGENT] Raw routing response: {result}")
    
    # Clean up the response - remove markdown code fences if present
    result = result.strip()
    if result.startswith("```"):
        # Remove markdown code fence
        result = result.replace("```json", "").replace("```", "").strip()
    
    # Ensure valid JSON response
    try:
        parsed = json.loads(result)
        llm_logger.debug(f"[ROUTE AGENT] Parsed JSON: agent={parsed.get('agent')}, subagent={parsed.get('subagent')}")
        return json.dumps(parsed)
    except json.JSONDecodeError as e:
        llm_logger.warning(f"[ROUTE AGENT] Invalid JSON from LLM: {result} | Error: {str(e)}")
        return json.dumps({"agent": None, "subagent": None})


def grok_call(prompt: str, max_tokens: int = 2048, temperature: float = 0.0) -> str:
    """
    Call Grok API using native Groq client.
    
    Args:
        prompt: The prompt to send to the LLM
        max_tokens: Maximum tokens in response
        temperature: Temperature for response generation (0.0 = deterministic)
    
    Returns:
        LLM response text
    """
    llm_logger.debug(f"[GROK CALL] Starting Grok API call...")
    llm_logger.debug(f"[GROK CONFIG] Model: {GROK_MODEL}, Max tokens: {max_tokens}, Temperature: {temperature}")
    llm_logger.debug(f"[GROK PROMPT] Length: {len(prompt)} chars")
    llm_logger.debug(f"[GROK PROMPT] Content:\n{prompt[:500]}..." if len(prompt) > 500 else f"[GROK PROMPT] Content:\n{prompt}")
    
    start_time = datetime.now()
    try:
        response = _grok_client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False
        )
        
        result = response.choices[0].message.content.strip()
        elapsed = (datetime.now() - start_time).total_seconds()
        
        llm_logger.debug(f"[GROK RESPONSE] Time: {elapsed:.2f}s")
        llm_logger.debug(f"[GROK RESPONSE] Length: {len(result)} chars")
        llm_logger.debug(f"[GROK RESPONSE] Content:\n{result[:500]}..." if len(result) > 500 else f"[GROK RESPONSE] Content:\n{result}")
        
        return result
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        llm_logger.error(f"[GROK ERROR] After {elapsed:.2f}s: {str(e)}")
        raise


# ============================
# AGENT INQUIRY (NEW)
# ============================
def answer_agent_inquiry(query: str, agents_data: dict) -> str:
    """
    Handle user queries about available agents and their capabilities.
    Directly answers questions based on ACTUAL agent data from database.
    """
    # Format all agents data with detailed capability information
    agents_text = _format_agents_hierarchy(agents_data["agents"])
    
    prompt = f"""You are a strict assistant answering questions about available agents. 
ONLY answer based on the exact capabilities listed below. DO NOT make up or assume capabilities.

User Query: {query}

Available Agents and Subagents with EXACT Capabilities:
{agents_text}

CRITICAL RULES:
1. ONLY mention capabilities that are EXPLICITLY listed in the agent descriptions above
2. If a capability is not mentioned, say the agent CANNOT do it
3. Answer YES only if the exact capability or similar capability is listed
4. Answer NO if the capability is not in the list
5. Be direct and factual - never assume or guess

Examples of CORRECT answers:
- User: "Can document agent create PPT?" 
  → Check: Is "ppt generation" or "powerpoint" in capabilities? NO → "No, the Document Creation Agent generates DOCX and PDF files, but PPT creation is not supported."
  
- User: "Can document agent create PDF?"
  → Check: Is "pdf generation" listed? YES → "Yes, the Document Creation Agent can generate PDF files."

Answer the user query based ONLY on the actual agent capabilities listed above:
"""

    llm_logger.debug(f"[AGENT INQUIRY] Answering agent question: {query[:100]}...")
    llm_logger.debug(f"[AGENT INQUIRY] Using Grok to answer agent inquiry")
    response = grok_call(prompt, max_tokens=1024, temperature=0.0)
    
    llm_logger.debug(f"[AGENT INQUIRY] Response length: {len(response)} chars")
    return response


def _format_agents_hierarchy(agents: list) -> str:
    """
    Format agents and subagents with detailed information.
    Shows main agent with name, description, and capabilities.
    Shows subagents with same format in hierarchical structure.
    """
    lines = []
    
    for agent in agents:
        # Main agent line with description
        agent_line = f"MAIN AGENT: {agent['name']}"
        lines.append(agent_line)
        
        # Agent description
        desc_line = f"  Description: {agent['description']}"
        lines.append(desc_line)
        
        # Agent capabilities
        if agent.get('capabilities'):
            caps = agent['capabilities']
            # If capabilities is a list, format as rows
            if isinstance(caps, list):
                caps_line = f"  Capabilities: {' | '.join(str(c) for c in caps)}"
            else:
                caps_line = f"  Capabilities: {caps}"
            lines.append(caps_line)
        
        # Subagents
        if agent.get('subagents'):
            for subagent in agent['subagents']:
                sub_name_line = f"  SUBAGENT: {subagent['name']}"
                lines.append(sub_name_line)
                
                sub_desc_line = f"    Description: {subagent['description']}"
                lines.append(sub_desc_line)
                
                # Subagent capabilities
                if subagent.get('capabilities'):
                    sub_caps = subagent['capabilities']
                    # If capabilities is a list, format as rows
                    if isinstance(sub_caps, list):
                        sub_caps_line = f"    Capabilities: {' | '.join(str(c) for c in sub_caps)}"
                    else:
                        sub_caps_line = f"    Capabilities: {sub_caps}"
                    lines.append(sub_caps_line)
        
        lines.append("")  # Blank line between agents
    
    return "\n".join(lines)


# ============================
# CONVERSATION MODE
# ============================
def handle_vague_query(query: str, agents_data: dict) -> str:
    """
    Handle vague, out of context, or meaningless queries.
    Asks clarification questions to better understand user intent.
    
    NOTE: For strong clarification with problem analysis, use 
    handle_vague_query_with_clarification() from conversation_service.py
    """
    agents_text = _format_agents_hierarchy(agents_data["agents"])
    
    prompt = f"""You are a helpful conversation assistant. The user query is vague, unclear, or out of context.

User Query: "{query}"

Available Agents and Subagents:
{agents_text}

TASK:
1. Analyze if the query is vague, meaningless, or out of context
2. If it is, ask a friendly clarification question to understand what they want
3. Suggest relevant agents they might be interested in based on available capabilities
4. If it makes sense, provide a helpful response

RESPONSE FORMAT:
Return a natural language response that:
- Acknowledges the vague query
- Asks clarification questions
- Suggests relevant agents or capabilities
- Is friendly and conversational

Response:
"""

    return grok_call(prompt, max_tokens=1024, temperature=0.0)


# ============================
# MESSAGE GENERATION
# ============================
def generate_routing_message(query: str, agent_name: str, subagent_name: str = None) -> str:
    """
    Generate a friendly, natural message for routing using LLM.
    Creates context-aware confirmation messages.
    """
    target_agent = subagent_name or agent_name
    
    prompt = f"""You are a helpful conversation assistant. Generate a brief, friendly, and natural confirmation message when routing a user to an agent.

User Query: "{query}"
Routing To: {target_agent}
Subagent: {subagent_name if subagent_name else "No (using main agent)"}

TASK:
Create a brief (1-2 sentences) natural message that:
1. Shows you understood the user's need based on their query
2. Confirms the routing decision
3. Is friendly and conversational
4. Does NOT sound robotic

IMPORTANT:
- Output ONLY the final message.
- Do NOT include any internal thought process, reasoning, or <think> blocks.
- Do NOT include any introductory text or "Here is the message".

Generate the message:
"""
    
    try:
        # Increased max_tokens slightly to ensure it can finish the thought and the message
        # though we want it to be very brief.
        message = grok_call(prompt, max_tokens=512, temperature=0.3)
        
        # Clean up the response (strip reasoning blocks if present)
        import re
        # Handle both closed and unclosed <think> blocks
        message = re.sub(r'<think>.*?(?:</think>|$)', '', message, flags=re.DOTALL).strip()
        
        # If the LLM still insists on a conversational preamble like "Message: "
        if ":" in message and len(message.split(":")[0]) < 20:
            potential_pains = ["Message", "Assistant", "Response", "Confirmation"]
            for pain in potential_pains:
                if message.startswith(f"{pain}:"):
                    message = message.split(":", 1)[1].strip()
                    break
        
        # Final trim for extra whitespace and quotes
        message = message.strip('"').strip()
        
        logger.info(f"Generated routing message: {message}")
        return message
    
    except Exception as e:
        logger.exception(f"Error generating routing message: {e}")
        # Fallback to default message
        return f"I understand your need. I'm routing you to the {target_agent} which can help you with this task."