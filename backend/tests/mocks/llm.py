"""
LLM Mocking Utilities

Provides mocks for LLM interactions to enable deterministic testing
of agent behavior without making actual API calls.
"""

from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, BaseMessage


class MockLLMResponse:
    """
    Represents a mock LLM response.

    Can be used to define expected responses for testing agent behavior.
    """

    def __init__(
        self,
        content: str = "",
        tool_calls: Optional[List[Dict]] = None,
        usage: Optional[Dict] = None,
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {"prompt_tokens": 10, "completion_tokens": 5}

    def to_message(self) -> AIMessage:
        """Convert to an AIMessage."""
        return AIMessage(
            content=self.content,
            tool_calls=self.tool_calls,
            usage_metadata=self.usage,
        )


class MockLLMFactory:
    """
    Factory for creating mock LLM instances with predefined responses.

    Example:
        factory = MockLLMFactory([
            MockLLMResponse("I'll help you"),
            MockLLMResponse("", tool_calls=[{"name": "read_file", "args": {"path": "test.py"}}]),
        ])

        mock_llm = factory.create()
    """

    def __init__(self, responses: Optional[List[MockLLMResponse]] = None):
        self.responses = responses or []
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

    def add_response(self, response: MockLLMResponse) -> "MockLLMFactory":
        """Add a response to the sequence."""
        self.responses.append(response)
        return self

    def add_text_response(self, text: str) -> "MockLLMFactory":
        """Convenience method to add a text-only response."""
        return self.add_response(MockLLMResponse(content=text))

    def add_tool_call(self, name: str, args: Dict[str, Any]) -> "MockLLMFactory":
        """Convenience method to add a tool call response."""
        return self.add_response(MockLLMResponse(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"call_{self.call_count}"}]
        ))

    def create(self) -> MagicMock:
        """Create a mock LLM instance."""
        mock = MagicMock()

        async def _ainvoke(messages: List[BaseMessage], **kwargs) -> AIMessage:
            self.call_count += 1
            self.call_history.append({
                "messages": messages,
                "kwargs": kwargs,
            })

            if self.call_count <= len(self.responses):
                return self.responses[self.call_count - 1].to_message()

            # Default response if exhausted
            return AIMessage(content="Default mock response")

        mock.ainvoke = _ainvoke
        mock.bind_tools = MagicMock(return_value=mock)

        return mock

    def assert_called_with_system_prompt(self, expected_substring: str) -> None:
        """Assert that a call was made with the given system prompt content."""
        for call in self.call_history:
            for msg in call["messages"]:
                if isinstance(msg, BaseMessage) and msg.type == "system":
                    if expected_substring in msg.content:
                        return

        raise AssertionError(
            f"No call found with system prompt containing: {expected_substring}"
        )

    def assert_tool_called(self, tool_name: str) -> None:
        """Assert that a specific tool was called."""
        for call in self.call_history:
            for msg in call["messages"]:
                if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls'):
                    for tc in msg.tool_calls:
                        if tc.get("name") == tool_name:
                            return

        raise AssertionError(f"Tool '{tool_name}' was not called")


def create_mock_llm(
    responses: Optional[List[Union[str, MockLLMResponse]]] = None
) -> MagicMock:
    """
    Quick factory for creating a mock LLM.

    Args:
        responses: List of response strings or MockLLMResponse objects

    Returns:
        Configured mock LLM
    """
    factory = MockLLMFactory()

    for resp in responses or ["Mock response"]:
        if isinstance(resp, str):
            factory.add_text_response(resp)
        else:
            factory.add_response(resp)

    return factory.create()


class LLMCallTracker:
    """
    Tracks LLM calls for later inspection.

    Use this to verify the prompts and parameters sent to the LLM.
    """

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def track(self, func: Callable) -> Callable:
        """Decorator to track function calls."""
        async def wrapper(*args, **kwargs):
            self.calls.append({
                "args": args,
                "kwargs": kwargs,
                "timestamp": __import__("time").time(),
            })
            return await func(*args, **kwargs)
        return wrapper

    def get_system_prompts(self) -> List[str]:
        """Extract all system prompts from tracked calls."""
        prompts = []
        for call in self.calls:
            messages = call["args"][0] if call["args"] else []
            for msg in messages:
                if isinstance(msg, BaseMessage) and msg.type == "system":
                    prompts.append(msg.content)
        return prompts

    def get_tool_calls(self) -> List[Dict]:
        """Extract all tool calls from tracked calls."""
        tool_calls = []
        for call in self.calls:
            messages = call["args"][0] if call["args"] else []
            for msg in messages:
                if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls'):
                    tool_calls.extend(msg.tool_calls)
        return tool_calls
