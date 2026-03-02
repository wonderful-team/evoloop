"""
Tool Mocking Utilities

Provides mocks for tool execution and registry.
"""

from typing import Any, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from langchain_core.tools import BaseTool


class MockTool:
    """
    Creates a mock tool for testing.

    Example:
        mock_read = MockTool.create(
            name="read_file",
            return_value="file content"
        )
    """

    @staticmethod
    def create(
        name: str,
        return_value: Any = None,
        side_effect: Optional[Callable] = None,
        description: str = "Mock tool",
    ) -> MagicMock:
        """Create a mock tool."""
        tool = MagicMock(spec=BaseTool)
        tool.name = name
        tool.description = description

        if side_effect:
            tool.ainvoke = AsyncMock(side_effect=side_effect)
            tool.invoke = MagicMock(side_effect=side_effect)
        else:
            tool.ainvoke = AsyncMock(return_value=return_value)
            tool.invoke = MagicMock(return_value=return_value)

        return tool

    @staticmethod
    def read_file(content: str = "test content") -> MagicMock:
        """Create a mock read_file tool."""
        return MockTool.create(
            name="read_file",
            return_value=content,
            description="Read file contents",
        )

    @staticmethod
    def write_file() -> MagicMock:
        """Create a mock write_file tool."""
        return MockTool.create(
            name="write_file",
            return_value="File written successfully",
            description="Write file contents",
        )

    @staticmethod
    def route_to() -> MagicMock:
        """Create a mock route_to tool."""
        return MockTool.create(
            name="route_to",
            return_value="Routed successfully",
            description="Route to another node",
        )

    @staticmethod
    def recall_memory(memories: List[str] = None) -> MagicMock:
        """Create a mock recall_memory tool."""
        return MockTool.create(
            name="recall_memory",
            return_value=memories or [],
            description="Recall memories",
        )


class MockToolRegistry:
    """Mock tool registry for testing."""

    def __init__(self):
        self.tools: Dict[str, MagicMock] = {}

    def register(self, tool: MagicMock) -> "MockToolRegistry":
        """Register a tool."""
        self.tools[tool.name] = tool
        return self

    def get(self, name: str) -> Optional[MagicMock]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_all(self) -> List[MagicMock]:
        """Get all registered tools."""
        return list(self.tools.values())

    def create_mock_registry(self) -> MagicMock:
        """Create a fully mocked registry."""
        registry = MagicMock()
        registry.get_tool = MagicMock(side_effect=self.get)
        registry.get_all_tools = MagicMock(return_value=self.get_all())
        registry.register = MagicMock(side_effect=self.register)
        return registry
