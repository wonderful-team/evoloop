"""
Tests for ToolState and ToolStateStore.
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from app.core.context.tool_state import ToolState, ToolStateStore, tool_state_store


@pytest.fixture
def clean_tool_store():
    """Provide clean tool store for each test."""
    store = ToolStateStore()
    store.clear_all()
    yield store
    store.clear_all()


class TestToolState:
    """Test ToolState dataclass."""

    def test_tool_state_creation(self):
        """Test creating ToolState instance."""
        state = ToolState(
            name="read_file",
            arguments='{"path": "/test.txt"}',
            start_time=1234567890.0,
            path="/test.txt",
            metadata={}
        )
        assert state.name == "read_file"
        assert state.path == "/test.txt"

    def test_get_summary_no_template(self):
        """Test summary without template."""
        state = ToolState(
            name="simple_tool",
            arguments="{}",
            start_time=0.0,
            metadata={}
        )
        output = "simple output"
        summary, is_file = state.get_summary(output)
        
        assert summary == "simple output"
        assert is_file is False

    def test_get_summary_with_truncation(self):
        """Test summary with long output truncation."""
        state = ToolState(
            name="long_output_tool",
            arguments="{}",
            start_time=0.0,
            metadata={}
        )
        # Create output > 500 chars
        output = "x" * 600
        summary, is_file = state.get_summary(output)
        
        assert "Truncated" in summary
        assert len(summary) < len(output)


class TestToolStateStore:
    """Test ToolStateStore singleton."""

    @pytest.mark.asyncio
    async def test_start_and_end_tool(self, clean_tool_store):
        """Test basic tool lifecycle."""
        thread_id = "thread-1"
        run_id = "run-1"
        
        # Start tool
        state = clean_tool_store.start_tool(
            thread_id=thread_id,
            run_id=run_id,
            name="test_tool",
            arguments="{}",
            path="/test"
        )
        
        assert state.name == "test_tool"
        assert state.path == "/test"
        
        # End tool
        ended_state = clean_tool_store.end_tool(thread_id, run_id)
        assert ended_state.name == "test_tool"
        
        # Second end should return None
        assert clean_tool_store.end_tool(thread_id, run_id) is None

    @pytest.mark.asyncio
    async def test_get_tool(self, clean_tool_store):
        """Test getting tool state."""
        thread_id = "thread-2"
        run_id = "run-2"
        
        # Get non-existent tool
        assert clean_tool_store.get_tool(thread_id, run_id) is None
        
        # Start and get
        clean_tool_store.start_tool(
            thread_id=thread_id,
            run_id=run_id,
            name="tool",
            arguments="{}"
        )
        
        state = clean_tool_store.get_tool(thread_id, run_id)
        assert state is not None
        assert state.name == "tool"

    @pytest.mark.asyncio
    async def test_get_duration(self, clean_tool_store):
        """Test duration calculation."""
        import time
        
        thread_id = "thread-3"
        run_id = "run-3"
        
        # Start tool
        clean_tool_store.start_tool(
            thread_id=thread_id,
            run_id=run_id,
            name="tool",
            arguments="{}"
        )
        
        # Small delay
        await asyncio.sleep(0.01)
        
        # Check duration
        duration = clean_tool_store.get_duration(thread_id, run_id)
        assert duration is not None
        assert duration >= 0.01

    @pytest.mark.asyncio
    async def test_clear_thread(self, clean_tool_store):
        """Test clearing thread state."""
        thread_id = "thread-4"
        
        clean_tool_store.start_tool(
            thread_id=thread_id,
            run_id="run-1",
            name="tool1",
            arguments="{}"
        )
        clean_tool_store.start_tool(
            thread_id=thread_id,
            run_id="run-2",
            name="tool2",
            arguments="{}"
        )
        
        # Clear thread
        clean_tool_store.clear_thread(thread_id)
        
        # All tools should be gone
        assert clean_tool_store.get_tool(thread_id, "run-1") is None
        assert clean_tool_store.get_tool(thread_id, "run-2") is None

    @pytest.mark.asyncio
    async def test_multiple_threads_isolation(self, clean_tool_store):
        """Test thread isolation."""
        thread_1 = "thread-a"
        thread_2 = "thread-b"
        
        # Add tool to thread 1
        clean_tool_store.start_tool(
            thread_id=thread_1,
            run_id="run-1",
            name="tool-a",
            arguments="{}"
        )
        
        # Add tool to thread 2
        clean_tool_store.start_tool(
            thread_id=thread_2,
            run_id="run-1",
            name="tool-b",
            arguments="{}"
        )
        
        # Verify isolation
        assert clean_tool_store.get_tool(thread_1, "run-1").name == "tool-a"
        assert clean_tool_store.get_tool(thread_2, "run-1").name == "tool-b"


class TestGlobalToolStateStore:
    """Test global tool_state_store instance."""

    def test_global_singleton(self):
        """Test that tool_state_store is singleton."""
        from app.core.context.tool_state import tool_state_store as store1
        from app.core.context.tool_state import tool_state_store as store2
        
        assert store1 is store2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
