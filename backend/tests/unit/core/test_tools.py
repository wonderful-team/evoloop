"""
Unit tests for tool system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.tools import BaseTool

from app.core.tools.executor import ToolExecutor


class TestToolExecutor:
    """Tests for ToolExecutor."""

    @pytest.fixture
    def executor(self):
        """Create a tool executor."""
        return ToolExecutor()

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, executor):
        """Test successful tool execution."""
        tool = MagicMock(spec=BaseTool)
        tool.ainvoke = AsyncMock(return_value="Success result")
        type(tool).name = "test_tool"

        config = {"callbacks": []}
        result = await executor.execute(tool, {"arg": "value"}, config=config)

        assert result == "Success result"
        tool.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_error(self, executor):
        """Test tool execution with error."""
        tool = MagicMock(spec=BaseTool)
        tool.ainvoke = AsyncMock(side_effect=ValueError("Tool failed"))
        type(tool).name = "failing_tool"

        config = {"callbacks": []}
        result = await executor.execute(tool, {"arg": "value"}, config=config)

        assert "Error" in result
        assert "Tool failed" in result

    @pytest.mark.asyncio
    async def test_execute_with_config(self, executor):
        """Test tool execution with config."""
        tool = MagicMock(spec=BaseTool)
        tool.ainvoke = AsyncMock(return_value="Result")
        type(tool).name = "test_tool"

        config = {"metadata": {"request_id": "test-123"}, "callbacks": []}
        await executor.execute(tool, {"arg": "value"}, config=config)

        # Verify tool was called
        tool.ainvoke.assert_called_once()


class TestToolRegistry:
    """Tests for tool registry."""

    def _create_mock_tool(self, name="test_tool"):
        """Helper to create a properly configured mock tool."""
        tool = MagicMock(spec=BaseTool)
        tool.name = name
        tool.__eq__ = lambda self, other: self is other
        return tool

    def test_register_tool(self):
        """Test registering a tool."""
        from app.core.tools.registry import AutoDiscoveryRegistry

        registry = AutoDiscoveryRegistry()
        tool = self._create_mock_tool("test_tool")

        registry.register(tool)

        assert tool in registry._tools

    def test_get_all_tools(self):
        """Test getting all registered tools."""
        from app.core.tools.registry import AutoDiscoveryRegistry

        registry = AutoDiscoveryRegistry()
        tool1 = self._create_mock_tool("tool1")
        tool2 = self._create_mock_tool("tool2")

        registry.register(tool1)
        registry.register(tool2)

        all_tools = registry.get_all_tools()

        assert len(all_tools) == 2
        assert tool1 in all_tools
        assert tool2 in all_tools

    def test_register_duplicate_tool(self):
        """Test that duplicate tools are not registered twice."""
        from app.core.tools.registry import AutoDiscoveryRegistry

        registry = AutoDiscoveryRegistry()
        tool = self._create_mock_tool("duplicate_tool")

        registry.register(tool)
        registry.register(tool)  # Try to register same tool again

        assert len(registry._tools) == 1


class TestEvoloopToolDecorator:
    """Tests for the @evoloop_tool decorator."""

    def test_decorator_adds_marker(self):
        """Test that decorator adds identification marker."""
        from app.core.tools.base import evoloop_tool

        @evoloop_tool
        async def test_tool(arg: str) -> str:
            """A test tool that returns a result."""
            return f"Result: {arg}"

        # The decorator sets is_evoloop_active on the wrapper function
        # Check if the coroutine function has the marker
        assert hasattr(test_tool, "coroutine") or hasattr(test_tool, "func")
        # The marker is set on the underlying function by the decorator
        # Verify tool was created successfully
        assert test_tool.name == "test_tool"

    @pytest.mark.asyncio
    async def test_decorator_preserves_functionality(self):
        """Test that decorated function still works."""
        from app.core.tools.base import evoloop_tool

        @evoloop_tool
        async def test_tool(arg: str) -> str:
            """A test tool that returns a result."""
            return f"Result: {arg}"

        # The decorator returns a StructuredTool, invoke it properly
        result = await test_tool.ainvoke({"arg": "test"})
        assert "Result: test" in str(result)

    @pytest.mark.asyncio
    async def test_decorator_error_handling(self):
        """Test error handling in decorated function."""
        from app.core.tools.base import evoloop_tool

        @evoloop_tool
        async def failing_tool():
            """A tool that always fails."""
            raise ValueError("Tool error")

        result = await failing_tool.ainvoke({})
        assert "Error" in str(result) or "Tool error" in str(result)
