"""
Query Validator Service

Validates user queries for relevance and quality before routing.
Uses confidence scoring to determine if a query should be processed,
rejected, or needs clarification.
"""

import json
from datetime import datetime
from typing import Dict, Any
from app.logger import logger


def validate_query(query: str, agents_data: dict) -> Dict[str, Any]:
    """
    Validate user query for relevance to application goals.
    
    Args:
        query: User's input query
        agents_data: Dictionary containing available agents and their capabilities
    
    Returns:
        Dictionary with validation results:
        {
            "is_valid": bool,
            "confidence": float (0.0 to 1.0),
            "reason": str,
            "suggested_action": str ("proceed", "clarify", "reject")
        }
    """
    logger.info(f"[QUERY VALIDATOR] Validating query: {query[:100]}...")
    
    # Import here to avoid circular dependency
    from app.services.llm_service import grok_call
    from app.services.llm_service import _format_agents_hierarchy
    
    # Format agents data for context
    agents_text = _format_agents_hierarchy(agents_data.get("agents", []))
    
    prompt = f"""You are a query validation system. Your job is to analyze if a user query is relevant and meaningful for our agent routing application.

User Query: "{query}"

Available Agents and Their Capabilities:
{agents_text}

VALIDATION CRITERIA:
1. **Relevance**: Does the query relate to any of the available agents or their capabilities?
2. **Clarity**: Is the query understandable and actionable?
3. **Intent**: Does the user have a clear task or goal?
4. **Meaningfulness**: Is the query meaningful (not gibberish, spam, or completely random)?

SCORING GUIDE:
- **0.9-1.0**: Perfect query - clear, relevant, actionable
- **0.7-0.89**: Good query - relevant but may need minor clarification
- **0.5-0.69**: Borderline - vague or unclear, needs clarification
- **0.3-0.49**: Poor query - barely relevant or very unclear
- **0.0-0.29**: Invalid query - gibberish, spam, or completely unrelated

SUGGESTED ACTIONS:
- **proceed**: Query is clear and relevant (confidence >= 0.7)
- **clarify**: Query is potentially valid but needs clarification (confidence 0.5-0.69)
- **reject**: Query is invalid or irrelevant (confidence < 0.5)

EXAMPLES:

Example 1 - Valid Query:
Query: "I need to send an email to my team"
Analysis: Clear intent, relates to email agent
Response: {{"is_valid": true, "confidence": 0.95, "reason": "Clear request for email sending functionality", "suggested_action": "proceed"}}

Example 2 - Vague Query:
Query: "help me"
Analysis: Too vague, no clear intent
Response: {{"is_valid": true, "confidence": 0.55, "reason": "Query is too vague - needs clarification on what help is needed", "suggested_action": "clarify"}}

Example 3 - Invalid Query:
Query: "asdfghjkl random stuff"
Analysis: Gibberish, no meaning
Response: {{"is_valid": false, "confidence": 0.15, "reason": "Query appears to be random text without clear meaning or intent", "suggested_action": "reject"}}

Example 4 - Unrelated Query:
Query: "What's the weather today?"
Analysis: Not related to any available agents
Response: {{"is_valid": false, "confidence": 0.25, "reason": "Query is unrelated to available agent capabilities (document creation, email, file management, etc.)", "suggested_action": "reject"}}

Example 5 - Borderline Query:
Query: "I want to do something with files"
Analysis: Relevant but unclear
Response: {{"is_valid": true, "confidence": 0.60, "reason": "Query relates to file operations but lacks specificity - needs clarification on what file operation", "suggested_action": "clarify"}}

Now analyze the user query and return ONLY a valid JSON response (no markdown, no code fence, no extra text):
{{
  "is_valid": <true or false>,
  "confidence": <0.0 to 1.0>,
  "reason": "<brief explanation>",
  "suggested_action": "<proceed, clarify, or reject>"
}}

JSON Response:
"""
    
    try:
        start_time = datetime.now()
        
        # Call Grok API for validation
        result = grok_call(prompt, max_tokens=256, temperature=0.0)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.debug(f"[QUERY VALIDATOR] Grok call completed in {elapsed:.2f}s")
        
        # Clean up response - remove markdown code fences if present
        result = result.strip()
        if result.startswith("```"):
            result = result.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON response
        validation_result = json.loads(result)
        
        # Validate response structure
        required_fields = ["is_valid", "confidence", "reason", "suggested_action"]
        if not all(field in validation_result for field in required_fields):
            logger.warning(f"[QUERY VALIDATOR] Invalid response structure: {validation_result}")
            return _get_fallback_validation(query)
        
        # Ensure confidence is a float between 0 and 1
        confidence = float(validation_result["confidence"])
        validation_result["confidence"] = max(0.0, min(1.0, confidence))
        
        logger.info(f"[QUERY VALIDATOR] Result: valid={validation_result['is_valid']}, "
                   f"confidence={validation_result['confidence']:.2f}, "
                   f"action={validation_result['suggested_action']}")
        
        return validation_result
        
    except json.JSONDecodeError as e:
        logger.error(f"[QUERY VALIDATOR] JSON decode error: {e} | Response: {result}")
        return _get_fallback_validation(query)
    
    except Exception as e:
        logger.error(f"[QUERY VALIDATOR] Validation error: {e}")
        return _get_fallback_validation(query)


def _get_fallback_validation(query: str) -> Dict[str, Any]:
    """
    Fallback validation when LLM call fails.
    Uses simple heuristics to determine query validity.
    """
    logger.warning("[QUERY VALIDATOR] Using fallback validation")
    
    # Simple heuristics
    query_lower = query.lower().strip()
    
    # Check for empty or very short queries
    if len(query_lower) < 3:
        return {
            "is_valid": False,
            "confidence": 0.2,
            "reason": "Query is too short to be meaningful",
            "suggested_action": "reject"
        }
    
    # Check for gibberish (no vowels or too many repeated characters)
    vowels = set('aeiou')
    has_vowels = any(c in vowels for c in query_lower)
    
    if not has_vowels:
        return {
            "is_valid": False,
            "confidence": 0.15,
            "reason": "Query appears to be random characters",
            "suggested_action": "reject"
        }
    
    # Check for common question words or action words
    action_words = ['send', 'create', 'make', 'generate', 'write', 'need', 'want', 
                   'help', 'can', 'how', 'what', 'rename', 'organize', 'manage']
    
    has_action = any(word in query_lower for word in action_words)
    
    if has_action:
        # Likely valid but may need clarification
        return {
            "is_valid": True,
            "confidence": 0.65,
            "reason": "Query contains action words but may need clarification",
            "suggested_action": "clarify"
        }
    
    # Default: borderline case
    return {
        "is_valid": True,
        "confidence": 0.55,
        "reason": "Unable to fully validate query - proceeding with caution",
        "suggested_action": "clarify"
    }


def format_rejection_message(validation_result: Dict[str, Any]) -> str:
    """
    Format a user-friendly rejection message based on validation result.
    
    Args:
        validation_result: Validation result dictionary
    
    Returns:
        User-friendly rejection message
    """
    reason = validation_result.get("reason", "Query could not be validated")
    confidence = validation_result.get("confidence", 0.0)
    
    base_message = f"I'm sorry, but I couldn't process your query. {reason}"
    
    if confidence < 0.3:
        # Very low confidence - likely gibberish or spam
        return (f"{base_message}\n\n"
                f"Please provide a clear question or request related to the available agents. "
                f"You can ask 'What agents are available?' to see what I can help you with.")
    else:
        # Low confidence - unrelated query
        return (f"{base_message}\n\n"
                f"I can help you with tasks related to document creation, email sending, "
                f"file management, and other agent-based operations. "
                f"Please rephrase your request or ask 'What can you help me with?' for more information.")
