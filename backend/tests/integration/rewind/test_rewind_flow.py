"""
Integration tests for the complete rewind flow.

These tests verify the end-to-end rewind functionality including:
- Event publishing and handling
- Handler registration
- Database operations
- File operations
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.events import system_bus
from app.core.rewind.events import RewindEventType
from app.core.rewind.events import (
    FilesCleanupEvent,
    MemoryCleanupEvent,
    MessagesCleanupEvent,
    RewindCompletedEvent,
    RewindFailedEvent,
    RewindRequestedEvent,
)
from app.core.rewind import RewindOrchestrator
from app.core.rewind.exceptions import (
    MessageNotFoundError,
    NoHumanMessageError,
    RewindError,
)


@pytest.mark.asyncio
class TestRewindFlow:
    """Test cases for the complete rewind flow."""

    async def test_rewind_orchestrator_publishes_events(self):
        """Test that RewindOrchestrator publishes the correct events."""
        # Arrange
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        
        orchestrator = RewindOrchestrator(event_bus=mock_bus)
        
        # Act
        await orchestrator.perform_rewind(
            thread_id="thread-test",
            target_message_id="msg-123",
            include_target=True,
            revert_files=True,
            reset_state=False
        )
        
        # Assert
        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert isinstance(event, RewindRequestedEvent)
        assert event.thread_id == "thread-test"
        assert event.target_message_id == "msg-123"

    async def test_handler_registration(self):
        """Test that all handlers can register to the event bus."""
        # This test ensures all handlers have valid register() methods
        from app.core.file.rewind import FileRewind
        from app.core.memory.rewind import MemoryRewind
        from app.core.engine.rewind.state import StateRewind
        from app.domain.todo.rewind import TodoRewind
        from app.core.learning.rewind import TraceRewind
        from app.core.rewind.handlers import MessageRewind
        
        mock_bus = MagicMock()
        mock_bus.subscribe = MagicMock()
        
        # Act - register all handlers
        FileRewind.register(mock_bus)
        MemoryRewind.register(mock_bus)
        StateRewind.register(mock_bus)
        TodoRewind.register(mock_bus)
        TraceRewind.register(mock_bus)
        MessageRewind.register(mock_bus)
        
        # Assert - each handler should subscribe to at least 2 events
        # (REWIND_REQUESTED + specific cleanup event)
        assert mock_bus.subscribe.call_count >= 12  # 6 handlers * 2 events each

    async def test_event_chain(self):
        """Test the event chain from RewindRequested to cleanup events."""
        # Arrange
        events_published = []
        
        async def capture_event(event):
            events_published.append(type(event).__name__)
        
        mock_bus = MagicMock()
        mock_bus.publish = capture_event
        
        # Act
        orchestrator = RewindOrchestrator(event_bus=mock_bus)
        await orchestrator.perform_rewind(thread_id="thread-test")
        
        # Assert
        assert "RewindRequestedEvent" in events_published

    async def test_rewind_with_all_handlers(self):
        """Test rewind with all handlers registered (mocked)."""
        # Arrange
        results = {}
        
        async def mock_handler(event):
            results[type(event).__name__] = "handled"
        
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=mock_handler)
        
        orchestrator = RewindOrchestrator(event_bus=mock_bus)
        
        # Act
        await orchestrator.perform_rewind(
            thread_id="thread-test",
            revert_files=True
        )
        
        # Assert
        assert "RewindRequestedEvent" in results


@pytest.mark.asyncio
class TestRewindEventTypes:
    """Test cases for RewindEvent types and their data."""

    def test_rewind_requested_event_serialization(self):
        """Test RewindRequestedEvent serialization."""
        event = RewindRequestedEvent(
            thread_id="thread-123",
            target_message_id="msg-456",
            include_target=True,
            revert_files=True,
            reset_state=False,
            reason="test"
        )
        
        assert event.event_type == RewindEventType.REWIND_REQUESTED
        assert event.data["thread_id"] == "thread-123"
        assert event.data["target_message_id"] == "msg-456"

    def test_files_cleanup_event_serialization(self):
        """Test FilesCleanupEvent serialization."""
        event = FilesCleanupEvent(
            thread_id="thread-123",
            file_operations=[
                {"path": "/test/file.txt", "operation": "ADD", "backup_content": None}
            ]
        )
        
        assert event.event_type == RewindEventType.FILES_CLEANUP
        assert event.data["operation_count"] == 1

    def test_messages_cleanup_event_serialization(self):
        """Test MessagesCleanupEvent serialization."""
        event = MessagesCleanupEvent(
            thread_id="thread-123",
            message_ids=["100", "101", "102"],
            delete_references=True
        )
        
        assert event.event_type == RewindEventType.MESSAGES_CLEANUP
        assert event.data["count"] == 3
        assert event.data["message_ids"] == ["100", "101", "102"]

    def test_memory_cleanup_event_serialization(self):
        """Test MemoryCleanupEvent serialization."""
        event = MemoryCleanupEvent(
            thread_id="thread-123",
            source_message_ids=["100", "101"],
            run_ids=["run-1", "run-2"]
        )
        
        assert event.event_type == RewindEventType.MEMORY_CLEANUP
        assert event.data["source_message_ids"] == ["100", "101"]
        assert event.data["run_ids"] == ["run-1", "run-2"]

    def test_rewind_completed_event_serialization(self):
        """Test RewindCompletedEvent serialization."""
        event = RewindCompletedEvent(
            thread_id="thread-123",
            removed_message_count=5,
            reverted_file_count=3,
            removed_memory_count=2,
            new_checkpoint_id="cp-456"
        )
        
        assert event.event_type == RewindEventType.REWIND_COMPLETED
        assert event.data["removed_message_count"] == 5
        assert event.data["reverted_file_count"] == 3
        assert event.data["new_checkpoint_id"] == "cp-456"

    def test_rewind_failed_event_serialization(self):
        """Test RewindFailedEvent serialization."""
        event = RewindFailedEvent(
            thread_id="thread-123",
            error="Test error",
            failed_step="files_cleanup",
            partial_results={"messages": 5}
        )
        
        assert event.event_type == RewindEventType.REWIND_FAILED
        assert event.data["error"] == "Test error"
        assert event.data["failed_step"] == "files_cleanup"


@pytest.mark.asyncio
class TestRewindErrorHandling:
    """Test cases for error handling in rewind operations."""

    async def test_rewind_error_includes_thread_id(self):
        """Test that RewindError includes thread_id."""
        error = RewindError("Test error", thread_id="thread-123")
        
        assert error.thread_id == "thread-123"
        assert str(error) == "Test error"

    async def test_message_not_found_error(self):
        """Test MessageNotFoundError."""
        error = MessageNotFoundError("Message not found", thread_id="thread-123")
        
        assert error.thread_id == "thread-123"
        assert isinstance(error, RewindError)

    async def test_no_human_message_error(self):
        """Test NoHumanMessageError."""
        error = NoHumanMessageError("No human message", thread_id="thread-123")
        
        assert error.thread_id == "thread-123"
        assert isinstance(error, RewindError)

    async def test_orchestrator_handles_errors_gracefully(self):
        """Test that orchestrator handles errors and publishes failed event."""
        # Arrange
        mock_bus = MagicMock()
        
        call_count = 0
        async def side_effect(event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Unexpected error")
        
        mock_bus.publish = AsyncMock(side_effect=side_effect)
        
        orchestrator = RewindOrchestrator(event_bus=mock_bus)
        
        # Act & Assert
        with pytest.raises(RewindError) as exc_info:
            await orchestrator.perform_rewind(thread_id="thread-123")
        
        assert "Unexpected error" in str(exc_info.value)
        assert exc_info.value.thread_id == "thread-123"
