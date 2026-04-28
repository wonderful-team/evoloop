#!/usr/bin/env python3
"""
Debug test for message storage mechanism.

This test verifies the complete flow from callback to database persistence.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


# Mock classes to simulate the message flow
@dataclass
class MockMessageCategory:
    value: str
    
    def is_visible_to_user(self) -> bool:
        visible = {
            "user", "assistant_response", "assistant_tool_call", 
            "tool_output", "internal_reasoning"
        }
        return self.value in visible
    
    def should_persist_to_db(self) -> bool:
        persisted = {
            "user", "assistant_response", "assistant_tool_call",
            "tool_output", "internal_reasoning", "error_business"
        }
        return self.value in persisted


@dataclass  
class MockHookResult:
    success: bool = True
    block: bool = False
    message: Optional[str] = None


class MockMessageClassifier:
    """Simplified message classifier"""
    
    @classmethod
    def classify_ai_message(cls, content: str, tool_calls: list = None, metadata: dict = None) -> MockMessageCategory:
        if metadata and metadata.get("is_error"):
            return MockMessageCategory("error_business")
        
        if tool_calls:
            return MockMessageCategory("assistant_tool_call")
        
        return MockMessageCategory("assistant_response")
    
    @classmethod
    def classify_tool_output(cls, tool_name: str, output: Any) -> MockMessageCategory:
        # Simulate: unknown_tool is treated as visible (is_hidden=False by default)
        return MockMessageCategory("tool_output")


class MockMessagePersistencePolicy:
    """Simplified persistence policy"""
    
    _RULES = {
        "user": (True, "content"),
        "assistant_response": (True, "content"),
        "assistant_tool_call": (True, "content"),
        "tool_output": (True, "content"),
        "internal_tool_call": (False, None),
        "internal_reasoning": (True, "thinking"),
        "error_business": (True, "content"),
    }
    
    @classmethod
    def apply_policy(cls, category: MockMessageCategory, content: str):
        should_persist, field = cls._RULES.get(category.value, (False, None))
        return {
            "should_persist": should_persist,
            "field": field,
            "category": category.value,
        }


class MockMessageHandler:
    """Simplified message handler for testing"""
    
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.persisted_messages = []
    
    async def handle_ai_message(self, content: str, tool_calls: list = None, metadata: dict = None):
        # 1. Classify
        category = MockMessageClassifier.classify_ai_message(content, tool_calls, metadata)
        
        # 2. Apply policy
        policy = MockMessagePersistencePolicy.apply_policy(category, content)
        
        # 3. Persist if needed
        if policy["should_persist"]:
            self.persisted_messages.append({
                "role": "ai",
                "content": content[:50] if content else "",
                "category": category.value,
            })
            persisted = True
        else:
            persisted = False
        
        return {
            "category": category.value,
            "persisted": persisted,
        }
    
    async def handle_tool_output(self, tool_name: str, output: str):
        # 1. Classify
        category = MockMessageClassifier.classify_tool_output(tool_name, output)
        
        # 2. Apply policy
        content = str(output) if output else ""
        policy = MockMessagePersistencePolicy.apply_policy(category, content)
        
        # 3. Persist if needed
        if policy["should_persist"]:
            self.persisted_messages.append({
                "role": "tool",
                "tool_name": tool_name,
                "content": content[:50] if content else "",
                "category": category.value,
            })
            persisted = True
        else:
            persisted = False
        
        return {
            "category": category.value,
            "persisted": persisted,
        }


class MockDatabaseCallbackHandler:
    """Simplified callback handler simulating the real one"""
    
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self._handler = MockMessageHandler(thread_id)
        self._tool_name_by_run_id = {}
        self._current_tool_name = "unknown_tool"
    
    async def on_llm_end(self, content: str, tool_calls: list = None):
        """Simulate LLM response handling"""
        try:
            result = await self._handler.handle_ai_message(
                content=content,
                tool_calls=tool_calls,
            )
            print(f"  [on_llm_end] content='{content[:30]}...', result={result}")
            return result
        except Exception as e:
            print(f"  [on_llm_end] ERROR: {e}")
            raise
    
    async def on_tool_start(self, serialized: dict, run_id: str):
        """Record tool start - currently COMMENTED OUT in real code!"""
        tool_name = serialized.get("name", "unknown_tool")
        self._tool_name_by_run_id[run_id] = tool_name
        self._current_tool_name = tool_name
        print(f"  [on_tool_start] tool={tool_name}, run_id={run_id}")
    
    async def on_tool_end(self, output: str, run_id: str):
        """Simulate tool completion handling"""
        try:
            # Get tool name (this is where the bug manifests)
            tool_name = self._tool_name_by_run_id.pop(run_id, None)
            if not tool_name:
                tool_name = self._current_tool_name  # Fallback to unknown_tool
            
            result = await self._handler.handle_tool_output(
                tool_name=tool_name,
                output=output,
            )
            print(f"  [on_tool_end] tool={tool_name}, result={result}")
            return result
        except Exception as e:
            print(f"  [on_tool_end] ERROR: {e}")
            raise


async def test_message_storage_flow():
    """Test the complete message storage flow"""
    print("=" * 70)
    print("Testing Message Storage Flow")
    print("=" * 70)
    
    handler = MockDatabaseCallbackHandler(thread_id="test-thread-123")
    
    # Test 1: Simple AI response (no tool calls)
    print("\n[Test 1] Simple AI response")
    result = await handler.on_llm_end("Hello! How can I help you?")
    assert result["persisted"] is True, "AI response should be persisted"
    print(f"  ✅ AI response persisted as {result['category']}")
    
    # Test 2: AI with tool calls
    print("\n[Test 2] AI with tool calls")
    result = await handler.on_llm_end(
        "I'll read the file for you",
        tool_calls=[{"name": "read_file", "args": {"path": "test.txt"}}]
    )
    assert result["persisted"] is True, "AI tool call should be persisted"
    print(f"  ✅ AI tool call persisted as {result['category']}")
    
    # Test 3: Tool output - WITH on_tool_start called (correct behavior)
    print("\n[Test 3] Tool output (with on_tool_start)")
    run_id = "run-001"
    await handler.on_tool_start({"name": "read_file"}, run_id)
    result = await handler.on_tool_end("File content: hello world", run_id)
    assert result["persisted"] is True, "Tool output should be persisted"
    assert result["category"] == "tool_output"
    print(f"  ✅ Tool output persisted as {result['category']}")
    
    # Test 4: Tool output - WITHOUT on_tool_start (simulates the bug)
    print("\n[Test 4] Tool output (WITHOUT on_tool_start - simulates bug)")
    handler2 = MockDatabaseCallbackHandler(thread_id="test-thread-456")
    # Skip on_tool_start - simulates the commented out code
    result = await handler2.on_tool_end("File content: hello world", "run-002")
    # Even with unknown_tool, it should still be persisted because is_hidden defaults to False
    assert result["persisted"] is True, "Tool output should still be persisted even with unknown_tool"
    print(f"  ✅ Tool output persisted as {result['category']} (even with unknown_tool)")
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary of persisted messages:")
    print("=" * 70)
    print(f"Handler 1 (with tool tracking): {len(handler._handler.persisted_messages)} messages")
    for msg in handler._handler.persisted_messages:
        print(f"  - {msg['role']}: {msg.get('category', 'unknown')}")
    
    print(f"\nHandler 2 (without tool tracking): {len(handler2._handler.persisted_messages)} messages")
    for msg in handler2._handler.persisted_messages:
        print(f"  - {msg['role']}: {msg.get('category', 'unknown')}")
    
    print("\n✅ All tests passed!")
    
    # Return analysis
    return {
        "handler1_count": len(handler._handler.persisted_messages),
        "handler2_count": len(handler2._handler.persisted_messages),
    }


if __name__ == "__main__":
    result = asyncio.run(test_message_storage_flow())
    print(f"\nFinal result: {result}")
