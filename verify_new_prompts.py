import sys
import os
import json
# Add the project root to sys.path to ensure absolute imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.services.conversation_service import ConversationSession, evaluate_user_response_for_routing, ask_progressive_clarification
from app.config import GROK_MODEL

# Mock agents data for testing
mock_agents_data = {
    "agents": [
        {
            "name": "Email Agent",
            "description": "Handles email composition and sending",
            "capabilities": ["send email", "compose"],
            "subagents": [
                {"name": "Composer", "description": "Writes email drafts", "capabilities": ["drafting"]},
                {"name": "Sender", "description": "Sends final emails", "capabilities": ["sending"]}
            ]
        },
        {
            "name": "Document Agent",
            "description": "Manages documents and files",
            "capabilities": ["create document", "read pdf"],
            "subagents": []
        }
    ]
}

def test_routing_evaluation():
    print(f"\n=== Testing Routing Evaluation (Model: {GROK_MODEL}) ===")
    session = ConversationSession("test_session")
    session.add_message("user", "I want to send an email")
    
    # Test ambiguous query
    print("\nQuery: 'I want to send an email' (Should be ambiguous/incomplete)")
    result = evaluate_user_response_for_routing(session, "I want to send an email", mock_agents_data)
    print(f"Result Keys: {result.keys()}")
    print(f"Route: {result.get('route')}")
    if not result.get('route'):
        candidates = result.get('matched_candidates', [])
        print(f"Matched Candidates: {len(candidates)}")
        for c in candidates:
            print(f"- {c.get('agent')} / {c.get('subagent')}: {c.get('reasoning')}")
        return candidates

    return []

def test_clarification(candidates):
    print("\n=== Testing Clarification Generation ===")
    session = ConversationSession("test_session")
    session.add_message("user", "I want to send an email")
    
    # Test clarification with candidates
    print(f"Generating clarification with {len(candidates)} candidates...")
    result = ask_progressive_clarification(session, mock_agents_data, candidates)
    print(f"\n--- CLARIFICATION RESPONSE ---\n")
    print(result.get('clarification_question'))
    print(f"\nSuggested Agents: {result.get('suggested_agents')}")

if __name__ == "__main__":
    try:
        candidates = test_routing_evaluation()
        test_clarification(candidates)
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()
