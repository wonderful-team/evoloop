"""
Tests for TransparentCallbackHandler.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.context import tool_state_store


@pytest.fixture
def mock_activity_monitor():
    """Mock activity monitor."""
    monitor = MagicMock()
    monitor.add_step = AsyncMock(return_value=1)
    monitor.update_step = AsyncMock()
    monitor.check_cancellation = AsyncMock()
    return monitor


@pytest.fixture
def clean_tool_store():
    """Clean tool store before/after test."""
    tool_state_store.clear_all()
    yield tool_state_store
    tool_state_store.clear_all()


@pytest.fixture
def handler(mock_activity_monitor):
    """Create handler with mocked dependencies."""
    with patch("app.core.callbacks.transparent.activity_monitor", mock_activity_monitor):
        with patch("app.core.callbacks.transparent.cache", MagicMock()):
            h = TransparentCallbackHandler(thread_id="test-thread")
            return h


class TestTransparentHandlerToolLifecycle:
    """Test tool lifecycle with tool_state_store."""

    @pytest.mark.asyncio
    async def test_tool_start_stores_state(self, handler, clean_tool_store):
        """Test that tool_start stores state in tool_state_store."""
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/test.txt"}',
            run_id="run-123"
        )
        
        # Verify state was stored
        state = clean_tool_store.get_tool("test-thread", "run-123")
        assert state is not None
        assert state.name == "read_file"
        assert state.path == "/test.txt"

    @pytest.mark.asyncio
    async def test_tool_end_uses_stored_state(self, handler, clean_tool_store):
        """Test that tool_end uses state from tool_state_store."""
        # Setup: Start tool first
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/test.txt"}',
            run_id="run-456"
        )
        
        # Execute tool end
        await handler.on_tool_end(
            output="File contents here",
            run_id="run-456"
        )
        
        # Verify state was removed
        state = clean_tool_store.get_tool("test-thread", "run-456")
        assert state is None

    @pytest.mark.asyncio
    async def test_multiple_tools_isolation(self, handler, clean_tool_store):
        """Test multiple tools don't interfere."""
        # Start two tools
        await handler.on_tool_start(
            serialized={"name": "tool_a"},
            input_str="{}",
            run_id="run-a"
        )
        await handler.on_tool_start(
            serialized={"name": "tool_b"},
            input_str="{}",
            run_id="run-b"
        )
        
        # Verify both exist
        assert clean_tool_store.get_tool("test-thread", "run-a").name == "tool_a"
        assert clean_tool_store.get_tool("test-thread", "run-b").name == "tool_b"
        
        # End first tool
        await handler.on_tool_end(output="result", run_id="run-a")
        
        # Verify only first was removed
        assert clean_tool_store.get_tool("test-thread", "run-a") is None
        assert clean_tool_store.get_tool("test-thread", "run-b") is not None


class TestTransparentHandlerSummaryLogic:
    """Test summary logic delegation to ToolState."""

    @pytest.mark.asyncio
    async def test_summary_generation_delegated(self, handler, clean_tool_store):
        """Test that summary generation uses ToolState.get_summary."""
        # Setup
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/test.txt"}',
            run_id="run-summary"
        )
        
        # Get the state
        state = clean_tool_store.get_tool("test-thread", "run-summary")
        
        # Verify get_summary method exists and works
        summary, is_file = state.get_summary("File content")
        assert isinstance(summary, str)
        assert isinstance(is_file, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
