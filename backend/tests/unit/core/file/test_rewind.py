"""
Unit tests for FileRewind handler.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from app.core.rewind.events import RewindEventType
from app.core.rewind.events import FilesCleanupEvent, RewindRequestedEvent
from app.core.file.rewind import FileRewind


class TestFileRewind:
    """Test cases for FileRewind handler."""

    @pytest.fixture
    def mock_event_bus(self):
        """Create a mock event bus."""
        bus = MagicMock()
        bus.subscribe = MagicMock()
        return bus

    @pytest.fixture
    def file_rewind(self):
        """Create a FileRewind instance."""
        return FileRewind()

    def test_register_subscribes_to_events(self, mock_event_bus):
        """Test that register subscribes to correct events."""
        # Act
        FileRewind.register(mock_event_bus)

        # Assert
        assert mock_event_bus.subscribe.call_count == 2
        
        # Check first subscription (FILES_CLEANUP)
        first_call = mock_event_bus.subscribe.call_args_list[0]
        assert first_call[0][0] == RewindEventType.FILES_CLEANUP
        
        # Check second subscription (REWIND_REQUESTED)
        second_call = mock_event_bus.subscribe.call_args_list[1]
        assert second_call[0][0] == RewindEventType.REWIND_REQUESTED

    @pytest.mark.asyncio
    async def test_handle_files_cleanup_add_operation(self, file_rewind, tmp_path):
        """Test handling ADD operation - should delete file."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        event = FilesCleanupEvent(
            thread_id="thread-123",
            file_operations=[{
                "id": 1,
                "message_id": 100,
                "path": str(test_file),
                "operation": "ADD",
                "backup_content": None
            }]
        )

        # Act
        await file_rewind._handle_files_cleanup(event)

        # Assert
        assert not test_file.exists()
        assert file_rewind.get_reverted_count() == 1

    @pytest.mark.asyncio
    async def test_handle_files_cleanup_edit_operation(self, file_rewind, tmp_path):
        """Test handling EDIT operation - should restore content."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("modified content")
        original_content = "original content"
        
        event = FilesCleanupEvent(
            thread_id="thread-123",
            file_operations=[{
                "id": 1,
                "message_id": 100,
                "path": str(test_file),
                "operation": "EDIT",
                "backup_content": original_content
            }]
        )

        # Act
        await file_rewind._handle_files_cleanup(event)

        # Assert
        assert test_file.read_text() == original_content
        assert file_rewind.get_reverted_count() == 1

    @pytest.mark.asyncio
    async def test_handle_files_cleanup_delete_operation(self, file_rewind, tmp_path):
        """Test handling DELETE operation - should restore file."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.unlink(missing_ok=True)  # Ensure file doesn't exist
        original_content = "deleted content"
        
        event = FilesCleanupEvent(
            thread_id="thread-123",
            file_operations=[{
                "id": 1,
                "message_id": 100,
                "path": str(test_file),
                "operation": "DELETE",
                "backup_content": original_content
            }]
        )

        # Act
        await file_rewind._handle_files_cleanup(event)

        # Assert
        assert test_file.exists()
        assert test_file.read_text() == original_content
        assert file_rewind.get_reverted_count() == 1

    @pytest.mark.asyncio
    async def test_handle_files_cleanup_no_backup(self, file_rewind, tmp_path, caplog):
        """Test handling EDIT without backup content - should warn."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("current content")
        
        event = FilesCleanupEvent(
            thread_id="thread-123",
            file_operations=[{
                "id": 1,
                "message_id": 100,
                "path": str(test_file),
                "operation": "EDIT",
                "backup_content": None
            }]
        )

        # Act
        with caplog.at_level("WARNING"):
            await file_rewind._handle_files_cleanup(event)

        # Assert
        assert "no backup" in caplog.text
        assert file_rewind.get_reverted_count() == 0

    @pytest.mark.asyncio
    async def test_handle_rewind_requested_disabled(self, file_rewind, mock_event_bus):
        """Test that rewind_requested does nothing when revert_files is False."""
        # Arrange
        event = RewindRequestedEvent(
            thread_id="thread-123",
            revert_files=False
        )

        # Act
        await file_rewind._handle_rewind_requested(event)

        # Assert - should not raise and should return early
        # No database operations should occur

    @pytest.mark.asyncio
    async def test_revert_files_processes_in_reverse_order(self, file_rewind, tmp_path):
        """Test that files are processed in reverse chronological order."""
        # Arrange
        test_file = tmp_path / "test.txt"
        
        operations = [
            {
                "id": 1,
                "message_id": 100,
                "path": str(test_file),
                "operation": "ADD",
                "backup_content": None,
                "created_at": "2024-01-01 10:00:00"
            },
            {
                "id": 2,
                "message_id": 101,
                "path": str(test_file),
                "operation": "EDIT",
                "backup_content": "version 1",
                "created_at": "2024-01-01 11:00:00"
            },
            {
                "id": 3,
                "message_id": 102,
                "path": str(test_file),
                "operation": "EDIT",
                "backup_content": "version 2",
                "created_at": "2024-01-01 12:00:00"
            }
        ]

        test_file.write_text("current")

        # Act
        count = await file_rewind._revert_files(operations)

        # Assert - should restore to version 2 (last edit)
        assert test_file.read_text() == "version 2"

    # ========================================================================
    # ICleanupHandler Interface Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_interface_add_operation(self, file_rewind, tmp_path):
        """Test ICleanupHandler.cleanup() with ADD operation."""
        # Arrange
        test_file = tmp_path / "cleanup_test.txt"
        test_file.write_text("to be deleted")
        
        # We need to mock the database query
        with patch("app.core.file.rewind.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                MagicMock(
                    id=1,
                    message_id=100,
                    file_path=str(test_file),
                    operation="ADD",
                    original_content=None
                )
            ]
            
            async_mock = MagicMock()
            async_mock.__aenter__ = AsyncMock(return_value=mock_session)
            async_mock.__aexit__ = AsyncMock(return_value=False)
            mock_session_scope.return_value = async_mock

            # Act
            count = await file_rewind.cleanup(["100"], revert_files=True)

        # Assert
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_cleanup_interface_revert_files_false(self, file_rewind):
        """Test ICleanupHandler.cleanup() with revert_files=False."""
        # Act
        count = await file_rewind.cleanup(["100"], revert_files=False)

        # Assert
        assert count == 0
