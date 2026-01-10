from fastapi import APIRouter
from typing import Union, Optional
import json
from datetime import datetime
from app.services.retrieval_service import retrieve_top_chunks
from app.services.llm_service import route_agent, answer_agent_inquiry, generate_routing_message
from app.services.agent_inquiry_service import is_agent_inquiry, get_all_agents_with_subagents
from app.services.query_validator_service import validate_query, format_rejection_message
from app.services.conversation_service import (
    get_or_create_session, 
    delete_session,
    ask_progressive_clarification,
    evaluate_user_response_for_routing,
    finalize_routing,
    ask_routing_confirmation,
    is_confirmation_response
)
from app.schemas import RoutingResponse, AgentInquiryResponse, ClarificationResponse, InvalidQueryResponse
from app.config import CONVERSATION_MODE, QUERY_VALIDATION_ENABLED, QUERY_VALIDATION_CONFIDENCE_THRESHOLD
from app.logger import logger, conversation_logger, routing_logger, user_logger

router = APIRouter(tags=["Chat"])

@router.post(
    "/chat",
    response_model=Union[RoutingResponse, AgentInquiryResponse, ClarificationResponse, InvalidQueryResponse],
    summary="Chat with the routing engine",
    description="Send a query to be routed to appropriate agent or retrieve agent information"
)
def chat(query: str, session_id: Optional[str] = None):
    """
    Process user queries with intelligent routing or agent inquiry.
    
    Supports CONVERSATION_MODE with 4-stage clarification pipeline:
    1. **Vague Query Detection**: Identifies unclear/out-of-context/meaningless queries
    2. **Agent Inquiry Handling**: Detects questions about available agents
    3. **Progressive Clarification**: Guides user toward clear routing intent
    4. **Confirmation**: Asks user to confirm agent selection before routing
    
    **CONVERSATION_MODE = True (Recommended):**
    - Automatically detects vague queries
    - Explains what's wrong with unclear questions
    - Provides assistant information and clarification guidance
    - Progressive clarification to narrow down agent selection
    - Asks for confirmation before final routing
    - Maintains conversation context across multiple turns
    
    **CONVERSATION_MODE = False:**
    - Direct routing based on semantic similarity
    - Faster but less interactive
    
    **Query Parameters:**
    - `query` (required): User query or task request
    - `session_id` (optional): Session ID for multi-turn conversation
    
    **Returns:** 
    - `agent_inquiry`: Information about available agents
    - `clarification`: Progressive clarification question or vague query feedback
    - `confirmation`: Ask user to confirm routing decision
    - `routing`: Final routing with agent/subagent selection
    """
    # ====== LOG: Request Details ======
    start_time = datetime.now()
    conversation_logger.info("=" * 80)
    conversation_logger.info(f"[NEW REQUEST] Session: {session_id or 'default_session'}")
    conversation_logger.info(f"[USER QUERY] {query}")
    conversation_logger.info(f"[CONFIG] CONVERSATION_MODE: {CONVERSATION_MODE}")
    conversation_logger.info(f"[CONFIG] QUERY_VALIDATION_ENABLED: {QUERY_VALIDATION_ENABLED}")
    
    # ====== USER LOG: Log user question ======
    user_logger.info("=" * 80)
    user_logger.info(f"User (Session: {session_id or 'default_session'}): {query}")
    
    
    # ====== GET SESSION ======
    # Get or create conversation session earlier to check state
    session = get_or_create_session(session_id or "default_session")
    
    # =====================================
    # STEP 0: QUERY VALIDATION (NEW)
    # =====================================
    # Skip validation if we are awaiting confirmation or clarification
    # as these responses (like "yes", "Agent A") might be flagged as invalid context-free
    is_ongoing_conversation = len(session.messages) > 0
    skip_validation = session.awaiting_confirmation or (CONVERSATION_MODE and is_ongoing_conversation)
    
    if QUERY_VALIDATION_ENABLED and not skip_validation:
        conversation_logger.info("[STAGE 0] Query validation enabled - validating query...")
        agents_data = get_all_agents_with_subagents()
        validation_result = validate_query(query, agents_data)
        
        conversation_logger.info(f"[VALIDATION] is_valid={validation_result['is_valid']}, "
                               f"confidence={validation_result['confidence']:.2f}, "
                               f"action={validation_result['suggested_action']}")
        
        # If query is invalid (low confidence), reject it
        if not validation_result["is_valid"]:
            rejection_message = format_rejection_message(validation_result)
            
            conversation_logger.info(f"[RESULT] Query rejected - confidence too low")
            conversation_logger.info(f"[RESPONSE TYPE] invalid_query")
            conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
            conversation_logger.info("=" * 80)
            
            user_logger.info("[ACTIVATED] Query Validation (Rejected)")
            user_logger.info(f"Assistant: {rejection_message}")
            user_logger.info("=" * 80)
            
            return {
                "type": "invalid_query",
                "response": rejection_message,
                "confidence": validation_result["confidence"],
                "suggested_action": validation_result["suggested_action"]
            }
        
        # If confidence is below threshold but not completely invalid, treat as vague
        if validation_result["confidence"] < QUERY_VALIDATION_CONFIDENCE_THRESHOLD:
            conversation_logger.info(f"[RESULT] Query has low confidence ({validation_result['confidence']:.2f}) - will trigger clarification")
            # Let it proceed to vague query handling in conversation mode
    elif skip_validation:
        conversation_logger.info(f"[STAGE 0] Skipping validation - Ongoing conversation (awaiting_conf={session.awaiting_confirmation})")
        agents_data = get_all_agents_with_subagents()
    else:
        conversation_logger.info("[STAGE 0] Query validation disabled - skipping validation")
        agents_data = get_all_agents_with_subagents()
    
    
    # =====================================
    # STEP 1: Check if agent inquiry
    # =====================================
    conversation_logger.info("[STAGE 1] Checking for agent inquiry...")
    if is_agent_inquiry(query):
        conversation_logger.info("[RESULT] Agent inquiry detected!")
        # agents_data already fetched in Step 0
        result = answer_agent_inquiry(query, agents_data)
        
        conversation_logger.info(f"[RESPONSE TYPE] agent_inquiry")
        conversation_logger.info(f"[RESPONSE LENGTH] {len(result)} characters")
        conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
        conversation_logger.info("=" * 80)
        
        # Log user response
        user_logger.info("[ACTIVATED] Agent Inquiry")
        user_logger.info(f"Assistant: {result}")
        user_logger.info("=" * 80)
        
        return {"type": "agent_inquiry", "response": result}
    
    conversation_logger.info("[RESULT] Not an agent inquiry, proceeding to routing...")
    
    # =====================================
    # STEP 2: Routing with Conversation Mode
    # =====================================
    if CONVERSATION_MODE:
        conversation_logger.info("[MODE] CONVERSATION_MODE = True")
        
        # session already fetched earlier
        session.add_message("user", query)
        # agents_data already fetched in Step 0
        
        conversation_logger.info(f"[SESSION] ID: {session.session_id}")
        conversation_logger.info(f"[SESSION] Clarifications asked so far: {session.clarifications_asked}")
        conversation_logger.info(f"[SESSION] Total messages in history: {len(session.messages)}")
        
        # Consolidation: Removed Step 2a (Vague Query Detection)
        # The new Mode 1 (Routing Evaluation) handles vague/unclear queries by naturally
        # returning route=false and candidates for clarification.
        
        # =====================================
        # STEP 2b: EVALUATE ROUTING READINESS
        # =====================================
        # =====================================
        # STEP 2b: EVALUATE ROUTING READINESS
        # =====================================
        conversation_logger.info("[STAGE 3] Evaluating routing readiness...")
        routing_decision = evaluate_user_response_for_routing(session, query, agents_data)
        
        # Store extracted parameters in session
        if routing_decision.get("client_name"):
            session.client_name = routing_decision.get("client_name")
        if routing_decision.get("wave_number"):
            session.wave_number = routing_decision.get("wave_number")
            
        # New Logic: Check 'route' boolean
        should_route = routing_decision.get("route", False)
        
        if should_route:
            agent_name = routing_decision.get("agent")
            subagent_name = routing_decision.get("subagent")
            confidence = routing_decision.get("confidence", 0)
            
            conversation_logger.info(f"[ROUTING DECISION] Agent: {agent_name}, Confidence: {confidence:.2%}")
            conversation_logger.info(f"[READY TO ROUTE] Yes | Confidence: {confidence:.2%}")
            
            # Mandatory confirmation (removing skip_confirmation logic)
            if not is_confirmation_response(query, session):
                conversation_logger.info("[STAGE 4] Asking for confirmation before routing...")
                session.clarifications_asked += 1
                session.awaiting_confirmation = True
                session.pending_routing_agent = agent_name
                session.pending_routing_subagent = subagent_name
                
                confirmation = ask_routing_confirmation(session, agent_name, subagent_name, agents_data)
                session.add_message("assistant", confirmation.get("confirmation_message", ""))
                
                conversation_logger.info(f"[RESPONSE TYPE] confirmation")
                conversation_logger.info(f"[PROPOSED ROUTING] Agent: {agent_name}, Subagent: {subagent_name}")
                conversation_logger.info(f"[AWAITING] User confirmation (confirm_routing=true)")
                conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
                conversation_logger.info("=" * 80)
                
                # Log user response
                user_logger.info(f"[ACTIVATED] Routing Confirmation (Proposed: {agent_name}/{subagent_name or 'main'})")
                user_logger.info(f"Assistant: {confirmation.get('confirmation_message', '')}")
                user_logger.info("=" * 80)
                
                return {
                    "type": "confirmation",
                    "response": confirmation.get("confirmation_message", ""),
                    "session_id": session.session_id,
                    "agent_name": agent_name,
                    "subagent_name": subagent_name,
                    "summary": confirmation.get("summary", ""),
                    "routing_target": confirmation.get("routing_target", "")
                }
            else:
                # User confirmed OR we are skipping confirmation (all parameters present)
                # CRITICAL CHECK: Even if confirmed, we MUST have parameters to route
                has_all_params = session.client_name and session.wave_number
                
                if not has_all_params:
                    conversation_logger.info("[STAGE 4] User confirmed agent, but parameters are missing. Asking for parameters...")
                    session.awaiting_confirmation = False # Reset confirmation flag
                    
                    # Call clarification to ask specifically for parameters
                    # since should_route was incorrectly True or we are in a confirmation state
                    clarification = ask_progressive_clarification(session, agents_data, [{"agent": agent_name, "subagent": subagent_name}])
                    session.add_message("assistant", clarification.get("clarification_question", ""))
                    
                    conversation_logger.info(f"[RESPONSE TYPE] clarification (for params)")
                    return {
                        "type": "clarification",
                        "response": clarification.get("clarification_question", ""),
                        "session_id": session.session_id,
                        "suggested_agents": clarification.get("suggested_agents", [])
                    }

                # =====================================
                # STEP 2d: FINAL ROUTING
                # =====================================
                conversation_logger.info("[STAGE 4] User confirmed - proceeding with routing...")
                conversation_logger.info(f"[FINAL ROUTING] Agent: {agent_name}, Subagent: {subagent_name}")
                
                # Clear confirmation flag
                session.awaiting_confirmation = False
                session.pending_routing_agent = None
                session.pending_routing_subagent = None
                
                result = finalize_routing(session, agent_name, subagent_name)
                session.add_message("assistant", f"Routing to {subagent_name or agent_name}")
                
                # Generate friendly routing message
                message = generate_routing_message(query, agent_name, subagent_name)
                
                routing_logger.info(f"[ROUTING COMPLETED] Agent: {agent_name}, Subagent: {subagent_name}")
                routing_logger.info(f"[CLARIFICATION ROUNDS] {session.clarifications_asked}")
                routing_logger.info(f"[FINAL MESSAGE] {message}")
                
                # Include client_name and wave_number in the routing JSON
                routing_payload = {
                    "agent": agent_name,
                    "subagent": subagent_name,
                    "client_name": session.client_name,
                    "wave_number": session.wave_number
                }
                
                # Clean up session after routing
                delete_session(session.session_id)
                conversation_logger.info(f"[SESSION] Cleaned up after routing")
                conversation_logger.info(f"[RESPONSE TYPE] routing")
                conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
                conversation_logger.info("=" * 80)
                
                # Log user response
                user_logger.info(f"[ACTIVATED] Routing (Direct/Confirmed)")
                user_logger.info(f"[ROUTED TO] {agent_name}" + (f"/{subagent_name}" if subagent_name else ""))
                user_logger.info(f"Assistant: {message}")
                user_logger.info("=" * 80)
                
                return {
                    "type": "routing",
                    "routing": json.dumps(routing_payload),
                    "message": message
                }
        else:
            # =====================================
            # STEP 2e: PROGRESSIVE CLARIFICATION
            # =====================================
            conversation_logger.info("[READY TO ROUTE] No - asking progressive clarification...")
            
            matched_candidates = routing_decision.get("matched_candidates", [])
            conversation_logger.info(f"[MATCHED CANDIDATES] {len(matched_candidates)} candidates found")
            
            session.clarifications_asked += 1
            
            # Pass matched_candidates to clarification function
            clarification = ask_progressive_clarification(session, agents_data, matched_candidates)
            session.add_message("assistant", clarification.get("clarification_question", ""))
            
            conversation_logger.info(f"[RESPONSE TYPE] clarification (progressive)")
            conversation_logger.info(f"[CLARIFICATION COUNT] {session.clarifications_asked}")
            conversation_logger.info(f"[SUGGESTED AGENTS] {clarification.get('suggested_agents', [])}")
            conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
            conversation_logger.info("=" * 80)
            
            # Log user response
            user_logger.info("[ACTIVATED] Clarification (Progressive)")
            user_logger.info(f"Assistant: {clarification.get('clarification_question', '')}")
            user_logger.info("=" * 80)
            
            return {
                "type": "clarification",
                "response": clarification.get("clarification_question", ""),
                "session_id": session.session_id,
                "clarification_count": session.clarifications_asked,
                "suggested_agents": clarification.get("suggested_agents", [])
            }
    
    # =====================================
    # STEP 3: Direct Routing (CONVERSATION_MODE = False)
    # =====================================
    conversation_logger.info("[MODE] CONVERSATION_MODE = False (Direct routing mode)")
    
    routing_logger.info("[STAGE] Direct routing (no clarification)")
    # Retrieve similar agents via vector search
    chunks = retrieve_top_chunks(query)
    routing_logger.info(f"[VECTOR SEARCH] Found {len(chunks)} similar agents")
    
    result = route_agent(query, chunks)
    
    routing_logger.info(f"[ROUTING RESULT] {result}")
    
    # Generate friendly message for routing
    try:
        routing_data = json.loads(result)
        agent_name = routing_data.get("agent")
        subagent_name = routing_data.get("subagent")
        message = generate_routing_message(query, agent_name, subagent_name)
    except Exception as e:
        conversation_logger.warning(f"Error generating message: {e}")
        message = "I understand your need. Routing to the appropriate agent."
    
    conversation_logger.info(f"[RESPONSE TYPE] routing")
    conversation_logger.info(f"[EXECUTION TIME] {(datetime.now() - start_time).total_seconds():.2f}s")
    conversation_logger.info("=" * 80)
    
    # Log user response
    routing_result = json.loads(result) if isinstance(result, str) else result
    user_logger.info(f"[ACTIVATED] Routing (Direct/Auto)")
    user_logger.info(f"[ROUTED TO] {routing_result.get('agent', 'Unknown')}")
    user_logger.info(f"Assistant: {message}")
    user_logger.info("=" * 80)
    
    return {"type": "routing", "routing": result, "message": message}


@router.post(
    "/chat/clear-session",
    summary="Clear conversation session",
    description="Clear a conversation session (useful for starting fresh)"
)
def clear_session(session_id: str):
    """Clear a conversation session by ID."""
    delete_session(session_id)
    return {"status": "ok", "message": f"Session {session_id} cleared"}
