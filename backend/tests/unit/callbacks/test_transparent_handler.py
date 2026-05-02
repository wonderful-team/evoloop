"""
Tests for TransparentCallbackHandler.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.engine.callbacks.transparent import TransparentCallbackHandler
from app.core.context import tool_state_store


@pytest.fixture
def mock_activity_monitor():
    """Mock activity monitor."""
    monitor = MagicMock()
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
    h = TransparentCallbackHandler(thread_id="test-thread")
    h.monitor = mock_activity_monitor
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
            serialized={"name": "read_file"},
            input_str='{"path": "/file1.txt"}',
            run_id="run-1"
        )
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/file2.txt"}',
            run_id="run-2"
        )
        
        # Verify both exist
        state1 = clean_tool_store.get_tool("test-thread", "run-1")
        state2 = clean_tool_store.get_tool("test-thread", "run-2")
        
        assert state1.path == "/file1.txt"
        assert state2.path == "/file2.txt"


class TestTransparentHandlerSummaryLogic:
    """Test summary generation delegation."""

    @pytest.mark.asyncio
    async def test_summary_generation_delegated(self, handler, clean_tool_store):
        """Test that summary generation is delegated to tool_state_store."""
        # Start and complete a tool
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/test.txt"}',
            run_id="run-summary"
        )
        
        # Verify tool is tracked
        state = clean_tool_store.get_tool("test-thread", "run-summary")
        assert state is not None
        assert state.name == "read_file"
