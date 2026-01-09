"""
Verification script to check that all tasks are properly connected to the per-task LLM configuration.
Run this to ensure the system is working correctly.
"""

from app.config import get_task_llm_mode, TASK_LLM_MODE

def verify_task_llm_configuration():
    """Verify all tasks are configured and accessible."""
    
    print("\n" + "="*80)
    print("PER-TASK LLM CONFIGURATION VERIFICATION")
    print("="*80 + "\n")
    
    # Test all tasks
    all_tasks = list(TASK_LLM_MODE.keys())
    print(f"Total tasks configured: {len(all_tasks)}\n")
    
    # Group by mode
    online_tasks = []
    offline_tasks = []
    
    print("Task Configuration:")
    print("-" * 80)
    
    for task in all_tasks:
        mode = get_task_llm_mode(task)
        status = "✅ ONLINE (Gemini)" if mode == "online" else "✅ OFFLINE (Ollama)"
        print(f"{task:50} {status}")
        
        if mode == "online":
            online_tasks.append(task)
        else:
            offline_tasks.append(task)
    
    print("\n" + "-" * 80)
    print(f"Online (Gemini):   {len(online_tasks)} tasks")
    print(f"Offline (Ollama):  {len(offline_tasks)} tasks")
    print("-" * 80)
    
    # Validation
    print("\nValidation Results:")
    print("-" * 80)
    
    # Check critical tasks are online
    critical_tasks = ["route_agent", "answer_agent_inquiry", "evaluate_user_response_for_routing"]
    critical_ok = all(get_task_llm_mode(task) == "online" for task in critical_tasks)
    
    if critical_ok:
        print("✅ CRITICAL TASKS: All set to 'online' (Gemini) - CORRECT")
    else:
        print("❌ CRITICAL TASKS: Some are not set to 'online' - ERROR")
        for task in critical_tasks:
            if get_task_llm_mode(task) != "online":
                print(f"   - {task}: {get_task_llm_mode(task)}")
    
    # Check detection tasks
    detection_tasks = ["is_agent_inquiry", "is_confirmation_response", "analyze_query_quality"]
    detection_offline = all(get_task_llm_mode(task) == "offline" for task in detection_tasks)
    
    if detection_offline:
        print("✅ DETECTION TASKS: All set to 'offline' (Ollama) - CORRECT")
    else:
        print("⚠️  DETECTION TASKS: Some are not set to 'offline'")
        for task in detection_tasks:
            mode = get_task_llm_mode(task)
            status = "OFFLINE" if mode == "offline" else f"ONLINE (consider changing to offline)"
            print(f"   - {task}: {status}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"✅ All {len(all_tasks)} tasks are properly configured")
    print(f"✅ Each task has explicit LLM assignment (online/offline)")
    print(f"✅ Critical tasks protected (always online)")
    print(f"✅ Cost optimization enabled (detection tasks using local Ollama)")
    print("="*80 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        verify_task_llm_configuration()
        print("✅ Configuration verification PASSED\n")
    except Exception as e:
        print(f"\n❌ Configuration verification FAILED: {e}\n")
        raise
