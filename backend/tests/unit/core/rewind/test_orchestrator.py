"""
Unit tests for RewindOrchestrator.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.rewind.events import RewindEventType
from app.core.rewind.events import (
    FilesCleanupEvent,
    MemoryCleanupEvent,
    MessagesCleanupEvent,
    RewindFailedEvent,
    RewindRequestedEvent,
)
from app.core.rewind import RewindOrchestrator
from app.core.rewind.exceptions import RewindError


class TestRewindOrchestrator:
    """Test cases for RewindOrchestrator."""

    @pytest.fixture
    def mock_event_bus(self):
        """Create a mock event bus."""
        bus = MagicMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def orchestrator(self, mock_event_bus):
        """Create a RewindOrchestrator with mock bus."""
        return RewindOrchestrator(event_bus=mock_event_bus)

    @pytest.mark.asyncio
    async def test_perform_rewind_publishes_requested_event(self, orchestrator, mock_event_bus):
        """Test that perform_rewind publishes RewindRequestedEvent."""
        # Act
        await orchestrator.perform_rewind(
            thread_id="thread-123",
            target_message_id="msg-456",
            include_target=True,
            revert_files=True,
            reset_state=False
        )

        # Assert
        mock_event_bus.publish.assert_called()
        call_args = mock_event_bus.publish.call_args[0][0]
        assert isinstance(call_args, RewindRequestedEvent)
        assert call_args.thread_id == "thread-123"
        assert call_args.target_message_id == "msg-456"
        assert call_args.include_target is True
        assert call_args.revert_files is True

    @pytest.mark.asyncio
    async def test_perform_rewind_with_defaults(self, orchestrator, mock_event_bus):
        """Test perform_rewind with default parameters."""
        # Act
        await orchestrator.perform_rewind(thread_id="thread-123")

        # Assert
        call_args = mock_event_bus.publish.call_args[0][0]
        assert call_args.thread_id == "thread-123"
        assert call_args.target_message_id is None
        assert call_args.include_target is True
        assert call_args.revert_files is True
        assert call_args.reset_state is False

    @pytest.mark.asyncio
    async def test_perform_rewind_returns_result(self, orchestrator, mock_event_bus):
        """Test that perform_rewind returns a RewindResult."""
        # Act
        result = await orchestrator.perform_rewind(thread_id="thread-123")

        # Assert
        assert result.status == "success"
        assert result.thread_id == "thread-123"

    @pytest.mark.asyncio
    async def test_perform_rewind_publishes_failed_event_on_error(self, orchestrator, mock_event_bus):
        """Test that perform_rewind publishes RewindFailedEvent on error."""
        # Arrange
        call_count = 0
        async def side_effect(event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
        
        mock_event_bus.publish.side_effect = side_effect

        # Act & Assert
        with pytest.raises(RewindError) as exc_info:
            await orchestrator.perform_rewind(thread_id="thread-123")
        
        assert "Test error" in str(exc_info.value)
        assert exc_info.value.thread_id == "thread-123"


class TestRewindEventTypes:
    """Test cases for RewindEventType enum."""

    def test_rewind_event_type_values(self):
        """Test that all event types have correct string values."""
        assert RewindEventType.REWIND_REQUESTED == "rewind.requested"
        assert RewindEventType.REWIND_COMPLETED == "rewind.completed"
        assert RewindEventType.REWIND_FAILED == "rewind.failed"
        assert RewindEventType.MESSAGES_CLEANUP == "rewind.messages.cleanup"
        assert RewindEventType.FILES_CLEANUP == "rewind.files.cleanup"
        assert RewindEventType.MEMORY_CLEANUP == "rewind.memory.cleanup"
        assert RewindEventType.TODO_CLEANUP == "rewind.todo.cleanup"
        assert RewindEventType.TRACE_CLEANUP == "rewind.trace.cleanup"
        assert RewindEventType.STATE_RESET == "rewind.state.reset"


class TestRewindModels:
    """Test cases for Rewind data models."""

    def test_rewind_request_creation(self):
        """Test RewindRequest creation."""
        from app.core.rewind import RewindRequest

        req = RewindRequest(
            thread_id="thread-123",
            target_message_id="msg-456",
            include_target=True,
            revert_files=True,
            reset_state=False,
            reason="test"
        )

        assert req.thread_id == "thread-123"
        assert req.target_message_id == "msg-456"
        assert req.include_target is True
        assert req.revert_files is True
        assert req.reset_state is False
        assert req.reason == "test"

    def test_rewind_request_defaults(self):
        """Test RewindRequest default values."""
        from app.core.rewind import RewindRequest

        req = RewindRequest(thread_id="thread-123")

        assert req.thread_id == "thread-123"
        assert req.target_message_id is None
        assert req.include_target is False
        assert req.revert_files is True
        assert req.reset_state is True
        assert req.reason == "user_request"

    def test_rewind_result_creation(self):
        """Test RewindResult creation."""
        from app.core.rewind import RewindResult

        result = RewindResult(
            status="success",
            thread_id="thread-123",
            removed_message_count=5,
            reverted_file_count=3,
            removed_memory_count=2
        )

        assert result.status == "success"
        assert result.thread_id == "thread-123"
        assert result.removed_message_count == 5
        assert result.reverted_file_count == 3
        assert result.removed_memory_count == 2

    def test_rewind_result_to_dict(self):
        """Test RewindResult.to_dict method."""
        from app.core.rewind import RewindResult

        result = RewindResult(
            status="success",
            thread_id="thread-123",
            removed_message_count=5,
            reverted_file_count=3
        )

        d = result.to_dict()

        assert d["status"] == "success"
        assert d["thread_id"] == "thread-123"
        assert d["removed_count"] == 5
        assert d["files_reverted"] == 3


class TestRewindExceptions:
    """Test cases for Rewind exceptions."""

    def test_rewind_error(self):
        """Test RewindError creation."""
        from app.core.rewind.exceptions import RewindError

        err = RewindError("Test error", thread_id="thread-123")

        assert str(err) == "Test error"
        assert err.thread_id == "thread-123"
        assert err.message == "Test error"

    def test_partial_rewind_error(self):
        """Test PartialRewindError creation."""
        from app.core.rewind.exceptions import PartialRewindError

        err = PartialRewindError(
            "Partial failure",
            thread_id="thread-123",
            completed_steps=["messages"],
            failed_steps=["files"],
            partial_results={"messages": 5}
        )

        assert str(err) == "Partial failure"
        assert err.thread_id == "thread-123"
        assert err.completed_steps == ["messages"]
        assert err.failed_steps == ["files"]
        assert err.partial_results == {"messages": 5}

    def test_message_not_found_error(self):
        """Test MessageNotFoundError."""
        from app.core.rewind.exceptions import MessageNotFoundError

        err = MessageNotFoundError("Message not found", thread_id="thread-123")

        assert str(err) == "Message not found"
        assert err.thread_id == "thread-123"

    def test_no_human_message_error(self):
        """Test NoHumanMessageError."""
        from app.core.rewind.exceptions import NoHumanMessageError

        err = NoHumanMessageError("No human message", thread_id="thread-123")

        assert str(err) == "No human message"
        assert err.thread_id == "thread-123"
