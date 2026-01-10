import json
from typing import Optional, List, Dict
from app.db.mysql import SessionLocal
from app.models.agent import Agent
from app.models.subagent import SubAgent
from app.logger import logger, conversation_logger
from app.services.llm_service import grok_call

# In-memory conversation store
# In production, use database for persistence
_conversations: Dict[str, Dict] = {}


class ConversationSession:
    """Manages a conversation session with progressive clarification."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict] = []  # Conversation history
        self.clarifications_asked = 0
        self.final_agent_id = None
        self.final_subagent_id = None
        self.is_finalized = False
        self.awaiting_confirmation = False  # Track if we just asked for confirmation
        self.pending_routing_agent = None
        self.pending_routing_subagent = None
        self.client_name = None
        self.wave_number = None
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history."""
        self.messages.append({"role": role, "content": content})
        msg_type = "USER" if role == "user" else "ASSISTANT"
        conversation_logger.debug(f"[SESSION {self.session_id}] {msg_type}: {content[:100]}..." if len(content) > 100 else f"[SESSION {self.session_id}] {msg_type}: {content}")
    
    def get_history_text(self) -> str:
        """Get formatted conversation history."""
        history = []
        for msg in self.messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            history.append(f"{role}: {msg['content']}")
        return "\n".join(history)
    
    def finalize(self, agent_id: int, subagent_id: Optional[int] = None):
        """Mark session as finalized with agent selection."""
        self.final_agent_id = agent_id
        self.final_subagent_id = subagent_id
        self.is_finalized = True
        conversation_logger.info(f"[SESSION {self.session_id}] FINALIZED - Agent: {agent_id}, Subagent: {subagent_id}, Total clarifications: {self.clarifications_asked}")


def get_or_create_session(session_id: str) -> ConversationSession:
    """Get existing conversation session or create new one."""
    if session_id not in _conversations:
        _conversations[session_id] = ConversationSession(session_id)
        conversation_logger.info(f"[SESSION {session_id}] CREATED - New conversation session")
    else:
        conversation_logger.debug(f"[SESSION {session_id}] RETRIEVED - Existing session, {len(_conversations[session_id].messages)} messages")
    return _conversations[session_id]


def delete_session(session_id: str):
    """Delete a conversation session."""
    if session_id in _conversations:
        del _conversations[session_id]
        logger.info(f"Deleted conversation session: {session_id}")


def ask_progressive_clarification(session: ConversationSession, agents_data: dict, matched_candidates: list = None) -> Dict:
    """
    Ask progressive clarification questions to narrow down agent selection.
    Uses matched candidates from routing evaluation to guide the user.
    """
    conversation_history = session.get_history_text()
    
    # Format candidates if available
    candidates_text = ""
    if matched_candidates:
        candidates_text = "Potentially Relevant Agents identified:\n"
        for cand in matched_candidates:
            candidates_text += f"- Agent: {cand.get('agent')} (Subagent: {cand.get('subagent')})\n"
            candidates_text += f"  Reasoning: {cand.get('reasoning')}\n"
    
    prompt = f"""You are an intelligent routing and clarification engine.
    
MODE 2: ask_progressive_clarification
--------------------------------------------------

INPUTS YOU RECEIVE:
- User query
- matched_candidates from evaluate_user_response_for_routing

YOUR GOAL:
1. If exactly ONE agent/subagent is clear from history or candidates: Collect missing required parameters (client_name and wave_number).
2. If NO agent is clear: Help the user choose the correct agent/subagent.

REQUIRED PARAMETERS:
- client_name: {session.client_name or 'MISSING'}
- wave_number: {session.wave_number or 'MISSING'}

RULES:
- If either client_name or wave_number is MISSING and you have a clear agent target:
  - ASK ONLY for the missing parameters. 
  - DO NOT ask the user to choose an agent again.
  - Example: "I've got the Document Creation Agent ready! I just need the client name and wave number to start."
- If NO agent is clear:
  - Provide a concise list of 2-3 matched_candidates and ask the user to choose.
- Be concise, friendly, and natural.
- Do NOT expose internal reasoning.

Conversation History:
{conversation_history}

{candidates_text}

OUTPUT FORMAT (PLAIN TEXT ONLY):

Structure:
1) One-line acknowledgement.
2) If parameters are missing: Ask for them specifically (e.g., "I just need the client name and wave number to proceed").
3) If agent selection is needed: Short list of options (bullet points) and a direct question.

EXAMPLE STYLE (FOR MISSING PARAMETERS):
"I understand you want to send an email! To get that started, could you please tell me the client name and the wave number?"

EXAMPLE STYLE (FOR AGENT SELECTION):
"I can help with this, but your request could fit a few areas. Please choose what you want to focus on:
• Agent A – Subagent X: <short description>
• Agent B – Subagent Y: <short description>

Which one should I proceed with?"

IMPORTANT:
- Do NOT add extra explanations
- Do NOT make assumptions
- Ask only ONE clear clarifying question
- Do NOT include any internal thought process, reasoning, or <think> blocks.
- Output ONLY the final natural message.
"""
    
    try:
        response = grok_call(prompt, max_tokens=1024, temperature=0.3)
        
        # Strip thinking blocks
        import re
        response = re.sub(r'<think>.*?(?:</think>|$)', '', response, flags=re.DOTALL).strip()
        
        response = response.strip()
        
        # Simple parsing since output is plain text
        # If response is empty, fallback
        if not response:
            return {
                "clarification_question": "I can help with that. Could you clarify which specific agent or task you'd like to proceed with?",
                "suggested_agents": []
            }
            
        return {
            "clarification_question": response,
            "suggested_agents": list(dict.fromkeys([c.get('agent') for c in matched_candidates])) if matched_candidates else []
        }

    except Exception as e:
        conversation_logger.exception(f"[SESSION {session.session_id}] Error generating clarification: {e}")
        return {
            "clarification_question": "I can help with that. Could you provide more details about what you'd like to do?",
            "suggested_agents": []
        }


def evaluate_user_response_for_routing(session: ConversationSession, user_response: str, agents_data: dict) -> Dict:
    """
    Evaluate user response to see if we have enough info to route to an agent.
    Returns:
    - dict with 'route': True/False and details
    """
    conversation_history = session.get_history_text()
    agents_text = _format_agents_with_categories(agents_data["agents"])
    
    prompt = f"""You are an intelligent routing and clarification engine.

MODE 1: evaluate_user_response_for_routing
--------------------------------------------------

INPUTS YOU RECEIVE:
- User query
- List of agents

YOUR GOAL:
Determine whether the user query clearly maps to exactly ONE agent and ONE subagent.

Conversation History:
{conversation_history}

Available Agents and Subagents:
{agents_text}

ANALYSIS RULES:
- Compare semantic meaning, intent, and task type — not just keywords.
- Prefer the most specific subagent over a general agent.
- Ignore partial or weak matches unless they strongly affect intent.
- If the query reasonably fits MORE THAN ONE agent or subagent, treat it as ambiguous.
- **EXTRACTION REQUIREMENT**: You MUST attempt to extract a `client_name` and `wave_number` from the ENTIRE conversation history or the current query.
- A `wave_number` is usually a number (e.g., "Wave 1", "2"). If you see "Wave X", extract "X" or "Wave X".
- A `client_name` is the name of a person or company (e.g., "Google", "Client A").
- If these were mentioned in previous turns, make sure to include them in your JSON response.
- Do NOT ignore them if they are in the history.

DECISION RULES (FOLLOW THESE EXACTLY):

1) If exactly ONE clear agent + subagent match exists AND both `client_name` and `wave_number` are known (either from this query or the history):
   - route = true
   - confidence = 0.8 to 1.0

2) If ANY mandatory parameter (`client_name` or `wave_number`) is missing:
   - route = false
   - Explain in `reasoning` exactly which parameters are missing.
   - You MUST return route = false even if the agent match is 100% certain.

3) If multiple agents or subagents are valid, OR the intent is unclear:
   - route = false
   - List the candidates in `matched_candidates`.

OUTPUT FORMAT (STRICT JSON ONLY - NO CONVERSATIONAL TEXT):

If route = true:
{{
  "route": true,
  "agent": "<agent_name>",
  "subagent": "<subagent_name or null>",
  "client_name": "<extracted_client_name>",
  "wave_number": "<extracted_wave_number>",
  "confidence": <number between 0 and 1>,
  "reasoning": "Concise explanation"
}}

If route = false:
{{
  "route": false,
  "client_name": "<extracted_client_name or null>",
  "wave_number": "<extracted_wave_number or null>",
  "matched_candidates": [
    {{
      "agent": "<agent_name>",
      "subagent": "<subagent_name or null>",
      "reasoning": "Why this candidate"
    }}
  ],
  "reasoning": "concise explanation"
}}

IMPORTANT:
- Return ONLY valid JSON.
- Do NOT include any introductory text, analysis, or explanation outside the JSON.
- Do NOT ask questions.
- Do NOT suggest next steps.
- Only evaluate and return the decision.

Analyze the query and return ONLY the JSON:
"""
    
    response = grok_call(prompt, max_tokens=1024, temperature=0.0)
    
    # Clean markdown if present
    response = response.strip()
    if response.startswith("```"):
        response = response.replace("```json", "").replace("```", "").strip()
    
    # Attempt to extract JSON if LLM included extra text
    if not (response.startswith("{") and response.endswith("}")):
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            response = json_match.group(0)
    
    try:
        result = json.loads(response)
        return result
    
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON from routing evaluation: {response}")
        # Return raw response as part of reasoning for debugging in verification results
        return {"route": False, "matched_candidates": [], "reasoning": f"JSON decode error: {response[:200]}"}


def _format_agents_with_categories(agents: list) -> str:
    """Format agents with categories for clarification context."""
    lines = []
    
    for agent in agents:
        lines.append(f"[AGENT] Name: {agent['name']}")
        lines.append(f"  Description: {agent['description']}")
        
        if agent.get('capabilities'):
            caps_str = " | ".join(agent['capabilities'])
            lines.append(f"  Capabilities: {caps_str}")
        
        if agent.get('subagents'):
            lines.append(f"  Subagents under {agent['name']}:")
            for subagent in agent['subagents']:
                lines.append(f"    [SUBAGENT] Name: {subagent['name']}")
                lines.append(f"      Description: {subagent['description']}")
                if subagent.get('capabilities'):
                    sub_caps = " | ".join(subagent['capabilities'])
                    lines.append(f"      Capabilities: {sub_caps}")
        
        lines.append("")
    
    return "\n".join(lines)


def analyze_query_quality(query: str, agents_data: dict) -> Dict:
    """
    Detect vague, out-of-context, or meaningless queries.
    Returns detailed analysis with problem identification and clarification guidance.
    
    Returns:
    {
        "is_vague": bool,
        "problem": str,  # Description of what's wrong with the query
        "assistant_info": str,  # What the assistant does
        "suggested_direction": str  # How to clarify the query
    }
    """
    conversation_logger.debug(f"[QUALITY CHECK] Analyzing query: {query[:100]}...")
    agents_text = _format_agents_with_categories(agents_data["agents"])
    
    prompt = f"""You are a query quality analyzer specialized in Open Negotiation workflows.

User Query: "{query}"

Available Agents and Subagents:
{agents_text}

ANALYSIS TASK:
Determine if this query is:
1. CLEAR & ACTIONABLE: Related to Open Negotiation workflow, specific enough to route
2. VAGUE: Related to workflow but too unclear (e.g., "do the open negotiation", "help me")
3. OUT-OF-CONTEXT: Unrelated to what the system does (e.g., "who is the president?")
4. INCOMPLETE: Missing important details for routing (e.g., "just the quality check")

Response Format (JSON):
{{
  "is_vague": true/false,
  "problem": "Specific explanation of what makes this query unclear/out-of-context",
  "assistant_info": "What this system handles (Open Negotiation workflow: quality checks, document creation, email sending, file organization)",
  "suggested_direction": "What information would make this query clear and actionable"
}}

IMPORTANT:
- For out-of-context queries, explain they're not related to Open Negotiation workflow
- For vague but in-scope queries, explain what details are missing
- Be specific, not generic - reference their actual query
- Focus on workflow stages (quality check, document creation, email sending, file organization) when suggesting direction

Analyze this specific query:
"""
    
    try:
        # Use Grok for quality analysis
        conversation_logger.debug(f"[QUALITY CHECK] Using Grok to analyze query")
        response = grok_call(prompt, max_tokens=512, temperature=0.0)
        
        response = response.strip()
        if response.startswith("```"):
            response = response.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(response)
        is_vague = result.get('is_vague', False)
        conversation_logger.info(f"[QUALITY CHECK] Analysis result: is_vague={is_vague}")
        if is_vague:
            conversation_logger.debug(f"[QUALITY CHECK] Problem: {result.get('problem')}")
        return result
    
    except Exception as e:
        conversation_logger.exception(f"[QUALITY CHECK] Error analyzing query: {e}")
        # Return safe fallback that won't crash system
        return {
            "is_vague": False,
            "problem": "",
            "assistant_info": "",
            "suggested_direction": ""
        }


def handle_vague_query_with_clarification(session: ConversationSession, query: str, agents_data: dict) -> Dict:
    """
    Handle vague, out-of-context, or meaningless queries with strong clarification.
    Tells user what's wrong with their question and guides them toward clarification.
    Dynamic and conversational - adapts to the actual user input.
    
    Returns clarification response with:
    - Explanation of the problem
    - Assistant information
    - Clear clarification question
    - Suggested agents to guide user
    """
    conversation_logger.info(f"[SESSION {session.session_id}] CLARIFICATION STAGE - Handling vague query: '{query}'")
    session.clarifications_asked += 1
    
    # Analyze the query quality
    analysis = analyze_query_quality(query, agents_data)
    conversation_logger.debug(f"[SESSION {session.session_id}] Analysis: vague={analysis.get('is_vague')}, problem={analysis.get('problem')}")
    
    agents_text = _format_agents_with_categories(agents_data["agents"])
    conversation_history = session.get_history_text()
    clarification_round = session.clarifications_asked
    
    # Build clarification prompt with problem explanation
    prompt = f"""You are a warm, helpful assistant handling a vague or unclear user query.

Conversation History:
{conversation_history}

Latest User Query: "{query}"

Problem Analysis:
- Is Vague: {analysis.get('is_vague', False)}
- Problem: {analysis.get('problem', 'Query is unclear')}
- This is clarification round #{clarification_round}

Available Agents and Subagents:
{agents_text}

CLARIFICATION TASK - CONTEXT MATTERS:
Your response must adapt to WHAT the user said, not follow a template:

IF query is completely OUT-OF-SCOPE (not related to the system):
- Politely explain what you CAN help with
- Be friendly but clear about boundaries
- Suggest the closest related task you can actually help with
- Ask if they have any tasks within your scope

IF query is VAGUE but IN-SCOPE (related to the work, but unclear):
- Acknowledge what they're trying to do
- Ask specific questions about the DETAILS they haven't mentioned
- Give examples of specific choices/options, not generic categories
- Focus on WHAT ASPECT they need help with

IF query mentions the domain but is too BROAD (like "do the whole thing"):
- Acknowledge they want to do the whole process
- Clarify if they want to do it step-by-step or focus on specific parts
- Ask if they're starting fresh or continuing
- Break down the workflow into specific phases they might choose

Guidelines for NATURAL responses:
- NO REPETITIVE STRUCTURE - don't use same format every time
- NO GENERIC LISTS - adapt examples to their specific situation
- EACH RESPONSE UNIQUE - sound like a human understanding their context
- PROGRESSIVE NARROWING - get progressively more specific as rounds increase
- Build on what they already said - don't ignore previous context

Response Format (JSON):
{{
  "acknowledgment": "Natural acknowledgment that fits THIS specific query",
  "what_we_do": "Explanation tailored to their situation",
  "clarifying_question": "Specific question(s) for THIS context",
  "example_questions": ["Contextual example 1", "Contextual example 2"],
  "suggested_agents": ["Most likely Agent1"]
}}

Generate a naturally conversational response UNIQUE to this query:
"""
    
    try:
        conversation_logger.debug(f"[SESSION {session.session_id}] Using Grok to generate clarification")
        response = grok_call(prompt, max_tokens=1024, temperature=0.3)
        
        response = response.strip()
        if response.startswith("```"):
            response = response.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(response)
        conversation_logger.debug(f"[SESSION {session.session_id}] Clarification generated")
        
        # Validate that we have actual content
        acknowledgment = result.get("acknowledgment", "").strip()
        what_we_do = result.get("what_we_do", "").strip()
        clarifying_question = result.get("clarifying_question", "").strip()
        example_questions = result.get("example_questions", [])
        
        # Build the final message with better structure
        message_parts = []
        
        # Add acknowledgment first (warm greeting/response)
        if acknowledgment:
            message_parts.append(acknowledgment)
        
        # Add what we do section if present
        if what_we_do:
            message_parts.append("")
            message_parts.append(what_we_do)
        
        # Add the clarifying question
        if clarifying_question:
            message_parts.append("")
            message_parts.append(clarifying_question)
        
        # Add example questions for guidance (if available)
        if example_questions and isinstance(example_questions, list) and example_questions:
            valid_examples = [ex.strip() for ex in example_questions if ex and ex.strip()]
            if valid_examples:
                message_parts.append("")
                message_parts.append("For example, you could tell me:")
                for ex in valid_examples:
                    message_parts.append(f"• {ex}")
        
        # Join all parts
        final_message = "\n".join(message_parts)
        
        # If we somehow got empty message, return a fallback
        if not final_message.strip():
            conversation_logger.warning(f"[SESSION {session.session_id}] LLM returned empty clarification fields")
            return {
                "clarification_question": "",
                "suggested_agents": [a["name"] for a in agents_data["agents"]],
                "acknowledgment": "",
                "what_we_do": ""
            }
        
        clarification_response = {
            "clarification_question": final_message,
            "suggested_agents": result.get("suggested_agents", [a["name"] for a in agents_data["agents"]]),
            "acknowledgment": acknowledgment,
            "what_we_do": what_we_do
        }
        
        # Add to session
        session.add_message("assistant", clarification_response["clarification_question"])
        return clarification_response
    
    except json.JSONDecodeError as e:
        conversation_logger.warning(f"[SESSION {session.session_id}] JSON decode error in clarification: {e}")
        conversation_logger.debug(f"[SESSION {session.session_id}] Raw response was: {response[:200]}")
        return {
            "clarification_question": "",
            "suggested_agents": [a["name"] for a in agents_data["agents"]],
            "acknowledgment": "",
            "what_we_do": ""
        }
    except Exception as e:
        conversation_logger.exception(f"[SESSION {session.session_id}] Error generating clarification: {e}")
        return {
            "clarification_question": "",
            "suggested_agents": [a["name"] for a in agents_data["agents"]],
            "acknowledgment": "",
            "what_we_do": ""
        }


def should_ask_clarification(query: str, agents_data: dict) -> bool:
    """
    Determine if a query is vague, out of context, or meaningless.
    Uses LLM to understand query intent.
    """
    analysis = analyze_query_quality(query, agents_data)
    is_vague = analysis.get("is_vague", False)
    logger.info(f"Query clarity check for '{query}': {'vague' if is_vague else 'clear'}")
    return is_vague


def ask_routing_confirmation(session: ConversationSession, agent_name: str, subagent_name: Optional[str], agents_data: dict) -> Dict:
    """
    Ask user for confirmation before routing to an agent.
    Shows what task will be handled and who will handle it.
    Dynamic confirmation endings - NOT templated.
    
    Returns confirmation message with:
    - Summary of what user asked for
    - Which agent/subagent will handle it
    - Option to confirm or ask for different routing
    """
    conversation_logger.info(f"[SESSION {session.session_id}] CONFIRMATION STAGE - Asking user to confirm routing to {agent_name}" + (f"/{subagent_name}" if subagent_name else ""))
    
    agents_text = _format_agents_with_categories(agents_data["agents"])
    conversation_history = session.get_history_text()
    
    prompt = f"""You are a helpful assistant confirming a user's agent routing decision.

Conversation History:
{conversation_history}

Proposed Routing:
- Agent: {agent_name}
- Subagent: {subagent_name if subagent_name else 'None (using main agent)'}

Available Agents and Subagents:
{agents_text}

DYNAMIC CONFIRMATION TASK:
Create a natural, conversational confirmation message that:
1. Reflects back what the user wants to do (show you understood)
2. Names the agent/subagent that will handle it
3. Briefly explains why this is the right choice
4. Asks for confirmation in a NATURAL WAY (NOT always "Does that sound correct?")

IMPORTANT:
- Output ONLY the final message inside the JSON field.
- Do NOT include any internal thought process, reasoning, or <think> blocks in the response.
- Keep the message to 1-2 sentences.

CRITICAL - VARY THE CONFIRMATION ENDINGS:
DO NOT use template endings like "Does that sound correct?" every time.
Instead, use dynamic endings based on the context, such as:
- "Ready to get started?"
- "Should we move forward with this?"
- "Want me to route you there?"
- "Let's do it?"
- "Shall I connect you?"
- "That work for you?"
- "Sound good?"
- "Alright with that plan?"
- Use natural language that matches the user's tone and the task type

GUIDANCE:
- For urgent/important tasks: More direct ("Ready to proceed?")
- For exploratory tasks: More casual ("Want to give it a try?")
- For routine tasks: More straightforward ("Should we move forward?")
- Match the personality/energy of the task

Keep it concise and natural. Avoid excessive formatting.

Response Format (JSON):
{{
  "summary": "What user wants to do - in their voice/context",
  "agent_description": "What this agent does",
  "confirmation_message": "Full natural message with varied ending - NOT templated"
}}

Generate a UNIQUE confirmation message with a NATURAL, VARIED ending:
"""
    
    try:
        conversation_logger.debug(f"[SESSION {session.session_id}] Using Grok to generate confirmation")
        response = grok_call(prompt, max_tokens=1024, temperature=0.3)
        
        # Strip thinking blocks
        import re
        response = re.sub(r'<think>.*?(?:</think>|$)', '', response, flags=re.DOTALL).strip()
        
        if response.startswith("```"):
            response = response.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(response)
        conversation_logger.debug(f"[SESSION {session.session_id}] Confirmation message generated for {agent_name}")
        
        # Use the LLM-generated confirmation message directly (no template assembly)
        confirmation_message = result.get('confirmation_message', '').strip()
        
        # If for some reason we got empty, use fallback
        if not confirmation_message:
            conversation_logger.warning(f"[SESSION {session.session_id}] LLM returned empty confirmation_message")
            target = f"{subagent_name}" if subagent_name else agent_name
            confirmation_message = f"I'll route you to {target}. Ready to proceed?"
        
        return {
            "confirmation_message": confirmation_message,
            "summary": result.get('summary', ''),
            "routing_target": f"{subagent_name}" if subagent_name else agent_name,
            "agent_description": result.get('agent_description', ''),
            "agent_name": agent_name,
            "subagent_name": subagent_name
        }
    
    except Exception as e:
        conversation_logger.exception(f"[SESSION {session.session_id}] Error generating confirmation: {e}")
        target = f"{subagent_name}" if subagent_name else agent_name
        # Return minimal fallback with only essential info
        return {
            "confirmation_message": f"Should I route you to {target}?",
            "summary": "",
            "routing_target": target,
            "agent_description": "",
            "agent_name": agent_name,
            "subagent_name": subagent_name
        }


def finalize_routing(session: ConversationSession, agent_name: str, subagent_name: Optional[str] = None) -> Dict:
    """
    Finalize the conversation with routing decision.
    Looks up agent IDs from database.
    """
    db = SessionLocal()
    try:
        # Find agent by name
        agent = db.query(Agent).filter(Agent.name == agent_name).first()
        if not agent:
            return {"error": f"Agent '{agent_name}' not found"}
        
        subagent_id = None
        if subagent_name:
            subagent = db.query(SubAgent).filter(
                SubAgent.agent_id == agent.id,
                SubAgent.name == subagent_name
            ).first()
            if subagent:
                subagent_id = subagent.id
        
        # Finalize session
        session.finalize(agent.id, subagent_id)
        
        return {
            "agent": agent_name,
            "subagent": subagent_name,
            "agent_id": agent.id,
            "subagent_id": subagent_id,
            "message": f"Great! Routing to {subagent_name or agent_name}"
        }
    
    finally:
        db.close()


def is_confirmation_response(query: str, session: ConversationSession) -> bool:
    """
    Check if user response is confirming a routing decision.
    Uses session state + LLM detection for reliability.
    """
    conversation_logger.debug(f"[CONFIRMATION CHECK] awaiting_confirmation={session.awaiting_confirmation}, query='{query}'")
    
    # If we're explicitly waiting for confirmation from our last message, check response
    if session.awaiting_confirmation:
        conversation_logger.info(f"[CONFIRMATION CHECK] System is awaiting confirmation. Checking if response is affirmative...")
        
        # Use LLM to detect if current response is affirmative
        affirmative_prompt = f"""Determine if this user response indicates agreement, confirmation, or approval.

User Response: \"{query}\"

Respond with ONLY \"yes\" or \"no\":
- \"yes\" if user is confirming, agreeing, or approving
- \"no\" otherwise

Answer:"""
        
        try:
            response = grok_call(
                affirmative_prompt,
                max_tokens=5,
                temperature=0.0
            )
            is_affirmative = response.strip().lower().startswith("yes")
            conversation_logger.info(f"[CONFIRMATION CHECK] LLM says affirmative={is_affirmative} for query='{query}'")
            return is_affirmative
        except Exception as e:
            conversation_logger.warning(f"[CONFIRMATION CHECK] LLM error: {e}, using fallback")
            # Fallback: check for affirmative keywords
            affirmative_keywords = ["yes", "yeah", "yep", "correct", "right", "sure", "ok", "okay", "agree", "proceed", "go"]
            is_affirmative = any(kw in query.lower() for kw in affirmative_keywords)
            conversation_logger.info(f"[CONFIRMATION CHECK] Fallback says affirmative={is_affirmative}")
            return is_affirmative
    
    conversation_logger.debug(f"[CONFIRMATION CHECK] Not awaiting confirmation, returning False")
    return False
