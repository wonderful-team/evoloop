"""
Tests for TraceRecorder - covering bugs found in code review.

Bugs to test:
1. on_tool_end type handling for non-string outputs
2. on_tool_end handling of complex/special objects
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


class TestTraceCallbackHandlerOnToolEnd:
    """Test on_tool_end method - Bug #3."""

    @pytest.fixture
    def handler(self):
        """Create a TraceCallbackHandler instance."""
        from app.core.learning.trace_recorder import TraceCallbackHandler
        return TraceCallbackHandler(thread_id="test_thread_123")

    @pytest.mark.asyncio
    async def test_on_tool_end_with_string_output(self, handler):
        """Test on_tool_end with normal string output."""
        output = "Tool execution result"

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="test_tool")

            mock_save.assert_called_once()
            # Verify it was called with tool_result action type
            args = mock_save.call_args
            if args.kwargs:
                assert args.kwargs.get("action_type") == "tool_result"
            else:
                # Positional args
                assert args.args[0] == "tool_result"

    @pytest.mark.asyncio
    async def test_on_tool_end_with_dict_output(self, handler):
        """Bug #3: Test on_tool_end with dict output (should be serialized)."""
        output = {"key": "value", "number": 42, "nested": {"a": 1}}

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="test_tool")

            mock_save.assert_called_once()
            # Get the payload that was passed
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            # The output should be a JSON string representation
            assert payload["name"] == "test_tool"
            assert payload["success"] is True
            assert isinstance(payload["output"], str)
            # Verify it's valid JSON and contains our data
            parsed = json.loads(payload["output"])
            assert parsed["key"] == "value"
            assert parsed["number"] == 42

    @pytest.mark.asyncio
    async def test_on_tool_end_with_list_output(self, handler):
        """Bug #3: Test on_tool_end with list output."""
        output = [1, 2, 3, "test", {"nested": True}]

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="list_tool")

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            assert isinstance(payload["output"], str)
            parsed = json.loads(payload["output"])
            assert parsed == [1, 2, 3, "test", {"nested": True}]

    @pytest.mark.asyncio
    async def test_on_tool_end_with_none_output(self, handler):
        """Bug #3: Test on_tool_end with None output."""
        output = None

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="none_tool")

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            assert payload["output"] == "null"  # JSON representation of None
            assert payload["name"] == "none_tool"

    @pytest.mark.asyncio
    async def test_on_tool_end_with_bytes_output(self, handler):
        """Bug #3: Test on_tool_end with bytes output (should use str())."""
        output = b"binary data"

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="bytes_tool")

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            # bytes should be converted to string representation
            output_str = payload["output"]
            assert "binary" in output_str or "b'" in output_str or "data" in output_str

    @pytest.mark.asyncio
    async def test_on_tool_end_output_truncation(self, handler):
        """Test that long outputs are truncated to 2000 chars."""
        output = "A" * 5000  # Very long string

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_end(output, name="long_tool")

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            # Should be truncated to 2000 chars
            assert len(payload["output"]) <= 2000

    @pytest.mark.asyncio
    async def test_on_tool_end_with_circular_reference(self, handler):
        """Bug #3: Test on_tool_end with circular reference (edge case)."""
        class Circular:
            def __str__(self):
                return "CircularObject"

        output = Circular()

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            # Should not raise even with complex objects
            await handler.on_tool_end(output, name="circular_tool")

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            # Should use str() fallback
            assert "Circular" in payload["output"]


class TestTraceCallbackHandlerOnToolStart:
    """Test on_tool_start method."""

    @pytest.fixture
    def handler(self):
        from app.core.learning.trace_recorder import TraceCallbackHandler
        return TraceCallbackHandler(thread_id="test_thread_123")

    @pytest.mark.asyncio
    async def test_on_tool_start_with_json_args(self, handler):
        """Test on_tool_start with valid JSON input_str."""
        # The serialized dict is parsed from input_str, not passed directly
        input_str = json.dumps({"param": "value", "other": "data"})

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_start(
                serialized={"name": "test_tool"},
                input_str=input_str
            )

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                assert args.kwargs.get("action_type") == "tool_call"
                payload = args.kwargs.get("payload", {})
            else:
                assert args.args[0] == "tool_call"
                payload = args.args[1]

            assert payload["name"] == "test_tool"
            # The args are parsed from input_str
            assert payload["args"]["param"] == "value"

    @pytest.mark.asyncio
    async def test_on_tool_start_with_invalid_json(self, handler):
        """Test on_tool_start with invalid JSON input_str."""
        input_str = "not valid json {"

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_tool_start(
                serialized={"name": "test_tool"},
                input_str=input_str
            )

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            assert payload["name"] == "test_tool"
            assert payload["args"]["raw"] == input_str


class TestTraceCallbackHandlerOnLLMEnd:
    """Test on_llm_end method."""

    @pytest.fixture
    def handler(self):
        from app.core.learning.trace_recorder import TraceCallbackHandler
        return TraceCallbackHandler(thread_id="test_thread_123")

    @pytest.mark.asyncio
    async def test_on_llm_end_with_content(self, handler):
        """Test on_llm_end captures LLM output."""
        # Mock LLMResult
        mock_result = MagicMock()
        mock_result.generations = [[MagicMock(text="LLM generated response")]]

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_llm_end(mock_result)

            mock_save.assert_called_once()
            args = mock_save.call_args
            if args.kwargs:
                payload = args.kwargs.get("payload", {})
            else:
                payload = args.args[1]

            assert payload["content"] == "LLM generated response"

    @pytest.mark.asyncio
    async def test_on_llm_end_empty_generations(self, handler):
        """Test on_llm_end with empty generations."""
        mock_result = MagicMock()
        mock_result.generations = []

        with patch.object(handler, '_save_event', new_callable=AsyncMock) as mock_save:
            await handler.on_llm_end(mock_result)

            mock_save.assert_not_called()


class TestTraceCallbackHandlerSanitizeSnapshot:
    """Test _sanitize_snapshot method."""

    @pytest.fixture
    def handler(self):
        from app.core.learning.trace_recorder import TraceCallbackHandler
        return TraceCallbackHandler(thread_id="test_thread_123")

    def test_sanitize_removes_environment_block(self, handler):
        """Test that environment_block is removed from snapshot."""
        state = {
            "messages": ["msg1", "msg2"],
            "environment_block": "huge string that should be removed",
            "current_plan": "some plan"
        }

        result = handler._sanitize_snapshot(state)

        assert "environment_block" not in result
        assert "messages" in result
        assert "current_plan" in result

    def test_sanitize_with_pydantic_model(self, handler):
        """Test sanitizing a Pydantic-like model."""
        class MockModel:
            def dict(self):
                return {"field1": "value1", "field2": "value2"}

        model = MockModel()
        result = handler._sanitize_snapshot(model)

        assert result["field1"] == "value1"
        assert result["field2"] == "value2"

    def test_sanitize_with_non_dict_non_model(self, handler):
        """Test sanitizing a primitive value."""
        result = handler._sanitize_snapshot("just a string")

        assert result["raw_state_type"] == "str"
        assert result["raw_state_value"] == "just a string"

    def test_sanitize_preserves_critical_fields(self, handler):
        """Test that critical fields like messages and current_plan are preserved."""
        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "current_plan": "step 1, step 2",
            "scratchpad": "some notes",
            "environment_block": "should be removed"
        }

        result = handler._sanitize_snapshot(state)

        assert "messages" in result
        assert "current_plan" in result
        assert "scratchpad" in result
        assert "environment_block" not in result


class TestSyncThreadToGraph:
    """Test sync_thread_to_graph function."""

    @pytest.mark.asyncio
    async def test_sync_with_no_events(self):
        """Test syncing a thread with no trace events."""
        from app.core.learning.trace_recorder import sync_thread_to_graph

        with patch('app.core.learning.trace_recorder.session_scope') as mock_scope:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch('app.core.learning.trace_recorder.memory_manager') as mock_memory:
                # Should not raise and should return early
                await sync_thread_to_graph(
                    thread_id="empty_thread",
                    project_id=1,
                    goal="Test goal"
                )

                # Memory manager should not be called since there are no events
                mock_memory.long_term.record_episode.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
