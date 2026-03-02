"""
Unit tests for callback handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTransparentCallbackHandler:
    """Tests for TransparentCallbackHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance with mocked monitor."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id="thread-123")
        handler.monitor = MagicMock()
        handler.monitor.add_step = AsyncMock(return_value=42)
        handler.monitor.update_step = AsyncMock()
        handler.monitor.check_cancellation = AsyncMock()
        return handler

    @pytest.mark.asyncio
    async def test_handler_init(self, handler):
        """Test handler initialization."""
        assert handler.thread_id == "thread-123"
        assert handler.current_task_id is None
        assert handler.active_llm_run_id is None

    @pytest.mark.asyncio
    async def test_on_llm_start_creates_task(self, handler):
        """Test that on_llm_start creates a task."""
        await handler.on_llm_start(
            serialized={},
            prompts=["test"],
            run_id="run-1"
        )

        assert handler.active_llm_run_id == "run-1"
        assert handler.current_task_id == 42
        handler.monitor.add_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_llm_start_skips_nested(self, handler):
        """Test that nested LLM calls are skipped."""
        handler.active_llm_run_id = "existing-run"

        await handler.on_llm_start(
            serialized={},
            prompts=["test"],
            run_id="run-2"
        )

        # Should not create a new task
        handler.monitor.add_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_llm_end_completes_task(self, handler):
        """Test that on_llm_end completes the task."""
        handler.active_llm_run_id = "run-1"
        handler.current_task_id = 42
        handler._current_stream_buffer = "content"

        await handler.on_llm_end(
            response=MagicMock(),
            run_id="run-1"
        )

        handler.monitor.update_step.assert_called_with("thread-123", 42, "done")
        assert handler.current_task_id is None
        assert handler.active_llm_run_id is None

    @pytest.mark.asyncio
    async def test_on_llm_error_fails_task(self, handler):
        """Test that on_llm_error marks task as failed."""
        handler.active_llm_run_id = "run-1"
        handler.current_task_id = 42

        await handler.on_llm_error(
            error=Exception("Test error"),
            run_id="run-1"
        )

        handler.monitor.update_step.assert_called_once()
        assert handler.current_task_id is None

    @pytest.mark.asyncio
    async def test_on_tool_start_creates_task(self, handler):
        """Test that on_tool_start creates a task."""
        await handler.on_tool_start(
            serialized={"name": "test_tool"},
            input_str='{"path": "/test"}'
        )

        assert handler.current_task_id == 42
        # Called twice: once for tool name, once for friendly name
        assert handler.monitor.add_step.call_count == 2

    @pytest.mark.asyncio
    async def test_on_tool_end_completes_task(self, handler):
        """Test that on_tool_end completes the task."""
        handler.current_task_id = 42
        handler.current_tool_name = "test_tool"

        await handler.on_tool_end(output="result")

        handler.monitor.update_step.assert_called_with("thread-123", 42, "done")
        assert handler.current_task_id is None

    @pytest.mark.asyncio
    async def test_check_cancellation(self, handler):
        """Test cancellation check."""
        await handler.on_llm_start({}, [], run_id="run-1")
        handler.monitor.check_cancellation.assert_called_with("thread-123")


class TestTransparentCallbackHandlerEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_handler_without_thread_id(self):
        """Test handler without thread ID."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id=None)
        handler.monitor = MagicMock()
        handler.monitor.add_step = AsyncMock(return_value=42)

        # Should not raise when no thread_id
        await handler.on_llm_start({}, [], run_id="run-1")
        assert handler.current_task_id is None

    @pytest.mark.asyncio
    async def test_on_tool_start_extracts_path(self):
        """Test that tool path is extracted from input."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id="thread-123")
        handler.monitor = MagicMock()
        handler.monitor.add_step = AsyncMock(return_value=42)
        handler.monitor.check_cancellation = AsyncMock()

        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "/test/file.txt"}'
        )

        assert handler.current_tool_path == "/test/file.txt"

    @pytest.mark.asyncio
    async def test_on_tool_start_with_literal_eval(self):
        """Test tool input parsing with literal_eval."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id="thread-123")
        handler.monitor = MagicMock()
        handler.monitor.add_step = AsyncMock(return_value=42)
        handler.monitor.check_cancellation = AsyncMock()

        # Single quotes (Python dict string)
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str="{'path': '/test/file.txt'}"
        )

        assert handler.current_tool_path == "/test/file.txt"


class TestTransparentCallbackHandlerChainCallbacks:
    """Tests for chain start/end callbacks."""

    @pytest.fixture
    def handler(self):
        """Create handler instance with mocked monitor."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id="thread-123")
        handler.monitor = MagicMock()
        handler.monitor.add_step = AsyncMock(return_value=100)
        handler.monitor.update_step = AsyncMock()
        return handler

    @pytest.mark.asyncio
    async def test_on_chain_start_logs_known_node(self, handler):
        """Test that chain_start logs known node names."""
        await handler.on_chain_start(
            serialized={},
            inputs={},
            metadata={"langgraph_node": "coder"},
            run_id="run-1"
        )

        handler.monitor.add_step.assert_called_once()
        assert "run-1" in handler._active_nodes

    @pytest.mark.asyncio
    async def test_on_chain_start_ignores_unknown_node(self, handler):
        """Test that chain_start ignores unknown node names."""
        await handler.on_chain_start(
            serialized={},
            inputs={},
            metadata={"langgraph_node": "unknown_internal_node"},
            run_id="run-1"
        )

        handler.monitor.add_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_chain_end_completes_node_task(self, handler):
        """Test that chain_end completes node task."""
        # Setup: add a node
        handler._active_nodes = {"run-1": (100, "coder")}

        await handler.on_chain_end(
            outputs={},
            run_id="run-1"
        )

        handler.monitor.update_step.assert_called_with("thread-123", 100, "done")
        assert "run-1" not in handler._active_nodes

    @pytest.mark.asyncio
    async def test_on_chain_error_fails_node_task(self, handler):
        """Test that chain_error marks node task as failed."""
        # Setup: add a node
        handler._active_nodes = {"run-1": (100, "coder")}

        await handler.on_chain_error(
            error=Exception("Node error"),
            run_id="run-1"
        )

        handler.monitor.update_step.assert_called_once()
        assert "run-1" not in handler._active_nodes


class TestTransparentCallbackHandlerTokenStreaming:
    """Tests for token streaming."""

    @pytest.fixture
    def handler(self):
        """Create handler instance with mocked monitor."""
        from app.core.callbacks.transparent import TransparentCallbackHandler

        handler = TransparentCallbackHandler(thread_id="thread-123")
        handler.monitor = MagicMock()
        handler.monitor.client = MagicMock()
        handler.monitor.client.publish = AsyncMock()
        handler.monitor.update_step = AsyncMock()
        handler.monitor.check_cancellation = AsyncMock()
        handler.active_llm_run_id = "run-1"
        handler.current_task_id = 42
        return handler

    @pytest.mark.asyncio
    async def test_on_llm_new_token_buffers_content(self, handler):
        """Test that tokens are buffered during streaming."""
        await handler.on_llm_new_token(
            token="Hello ",
            run_id="run-1"
        )
        await handler.on_llm_new_token(
            token="World",
            run_id="run-1"
        )

        assert handler._current_stream_buffer == "Hello World"

    @pytest.mark.asyncio
    async def test_on_llm_new_token_ignores_wrong_run_id(self, handler):
        """Test that tokens from wrong run_id are ignored."""
        await handler.on_llm_new_token(
            token="Hello",
            run_id="different-run"
        )

        assert handler._current_stream_buffer == ""

    @pytest.mark.asyncio
    async def test_on_llm_new_token_publishes_on_newline(self, handler):
        """Test that buffered content is published on newline."""
        await handler.on_llm_new_token(
            token="Line1\nLine2",
            run_id="run-1"
        )

        handler.monitor.client.publish.assert_called_once()
