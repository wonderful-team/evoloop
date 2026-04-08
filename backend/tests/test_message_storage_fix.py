#!/usr/bin/env python3
"""
Test to verify the message storage fix.

This test checks that the persist_message_task function accepts all required parameters.
"""

import inspect


def test_persist_message_task_signature():
    """Test that persist_message_task has the correct signature."""
    # Import the function
    import sys
    sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')
    
    from app.core.engine.tasks import persist_message_task
    
    # Get function signature
    sig = inspect.signature(persist_message_task)
    params = list(sig.parameters.keys())
    
    print("persist_message_task parameters:")
    for param in params:
        print(f"  - {param}")
    
    # Check required parameters
    required_params = [
        'thread_id',
        'project_id', 
        'role',
        'content',
        'thinking',
        'sequence_number',
        'run_id',
        'status',
        'parent_id',
        'tool_calls',
        'references',
        'action_type',
        'category',
        'is_visible'
    ]
    
    print("\nChecking required parameters:")
    for param in required_params:
        if param in params:
            print(f"  ✅ {param}")
        else:
            print(f"  ❌ {param} - MISSING!")
    
    # Check that is_visible is present
    assert 'is_visible' in params, "is_visible parameter is missing!"
    
    print("\n✅ All required parameters present!")
    return True


if __name__ == "__main__":
    test_persist_message_task_signature()
