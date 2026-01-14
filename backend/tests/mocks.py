from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeListChatModel(BaseChatModel):
    """
    A Fake Chat Model that returns pre-defined responses.
    Useful for deterministic testing of Agent flows.
    """
    responses: list[BaseMessage]
    i: int = 0
    request_history: list[list[BaseMessage]] = []

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        # Record the incoming messages for verification
        self.request_history.append(messages)

        if self.i < len(self.responses):
            response = self.responses[self.i]
            self.i += 1
        else:
            response = AIMessage(content="[MOCK] No more responses defined.")

        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "fake-list-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any):
        """Mock bind_tools to return self (ignoring tools)"""
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any):
        """Mock structured output to return self or a specific runnable"""
        return self

class MockToolExecutor:
    """
    Mocks the ToolExecutor to verify tool calls without running them.
    """
    def __init__(self):
        self.calls = []

    async def execute(self, tool, args, config=None):
        self.calls.append({"tool": tool.name, "args": args})
        return f"Mock output for {tool.name}"
