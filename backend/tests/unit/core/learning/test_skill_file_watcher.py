"""
Functional tests for SkillsFileWatcher — File → DB sync via watchdog.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.file.event import FileSystemEventType
from app.core.learning.skill_file_watcher import (
    SkillsFileWatcher,
    _handle_file_created,
    _handle_file_modified,
    _handle_file_deleted,
    _handle_directory_deleted,
    _is_skill_md,
    skills_file_watcher,
)


@pytest.fixture(autouse=True)
def reset_watcher():
    """Reset singleton state between tests."""
    skills_file_watcher._subscribed = False
    skills_file_watcher._watcher = None
    yield


# =============================================================================
# Utility helpers
# =============================================================================

class TestIsSkillMd:

    @pytest.mark.parametrize("path,expected", [
        ("SKILL.md", True),
        ("foo/SKILL.md", True),
        ("/a/b/SKILL.md", True),
        ("foo.py", False),
        ("SKILL.txt", False),
        ("skills.md", False),
    ])
    def test_skill_md_filter(self, path, expected):
        assert _is_skill_md(path) is expected


# =============================================================================
# Event handler unit tests
# =============================================================================

class MockFileEvent:
    """Minimal event-like object for testing handlers."""

    def __init__(self, path, is_directory=False):
        self.data = {"path": path, "is_directory": is_directory}


class TestHandleFileCreated:

    @pytest.mark.asyncio
    async def test_skill_md_created_triggers_import(self, tmp_path):
        """SKILL.md created → calls import_skill_from_disk."""
        skill_md = tmp_path / "roles" / "my_skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("test")
        event = MockFileEvent(str(skill_md))

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.import_skill_from_disk",
            new_callable=AsyncMock,
        ) as mock_import:
            await _handle_file_created(event)
            mock_import.assert_called_once_with(str(skill_md))

    @pytest.mark.asyncio
    async def test_non_skill_file_ignored(self):
        """Non-SKILL.md file event → no import."""
        event = MockFileEvent("/some/file.txt")

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.import_skill_from_disk",
            new_callable=AsyncMock,
        ) as mock_import:
            await _handle_file_created(event)
            mock_import.assert_not_called()


class TestHandleFileModified:

    @pytest.mark.asyncio
    async def test_skill_md_modified_triggers_import(self, tmp_path):
        """SKILL.md modified → calls import_skill_from_disk."""
        skill_md = tmp_path / "roles" / "my_skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("test")
        event = MockFileEvent(str(skill_md))

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.import_skill_from_disk",
            new_callable=AsyncMock,
        ) as mock_import:
            await _handle_file_modified(event)
            mock_import.assert_called_once_with(str(skill_md))

    @pytest.mark.asyncio
    async def test_non_skill_file_ignored(self):
        """Non-SKILL.md modified → no action."""
        event = MockFileEvent("/some/file.txt")

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.import_skill_from_disk",
            new_callable=AsyncMock,
        ) as mock_import:
            await _handle_file_modified(event)
            mock_import.assert_not_called()


class TestHandleFileDeleted:

    @pytest.mark.asyncio
    async def test_skill_md_deleted_triggers_remove(self):
        """SKILL.md deleted → calls delete_skill_by_path."""
        event = MockFileEvent("/skills/roles/my_skill/SKILL.md")

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.delete_skill_by_path",
            new_callable=AsyncMock,
        ) as mock_delete:
            await _handle_file_deleted(event)
            mock_delete.assert_called_once_with(
                "/skills/roles/my_skill/SKILL.md"
            )

    @pytest.mark.asyncio
    async def test_non_skill_file_ignored(self):
        """Non-SKILL.md deleted → no action."""
        event = MockFileEvent("/some/other.txt")

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.delete_skill_by_path",
            new_callable=AsyncMock,
        ) as mock_delete:
            await _handle_file_deleted(event)
            mock_delete.assert_not_called()


class TestHandleDirectoryDeleted:

    @pytest.mark.asyncio
    async def test_directory_deleted_triggers_remove(self):
        """Directory deleted → calls delete_skill_by_path with SKILL.md path."""
        event = MockFileEvent("/skills/roles/my_skill")

        with patch(
            "app.core.learning.skill_file_watcher.skill_sync_service.delete_skill_by_path",
            new_callable=AsyncMock,
        ) as mock_delete:
            await _handle_directory_deleted(event)
            mock_delete.assert_called_once_with(
                "/skills/roles/my_skill/SKILL.md"
            )


# =============================================================================
# SkillsFileWatcher lifecycle
# =============================================================================

class TestSkillsFileWatcher:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.skills_dir = tmp_path / "skills"
        self.skills_dir.mkdir()

    @pytest.mark.asyncio
    async def test_start_creates_watcher(self):
        """start() → FileWatcher created and started, events subscribed."""
        with patch(
            "app.core.learning.skill_file_watcher.FileWatcher"
        ) as MockWatcher:
            mock_watcher = MagicMock()
            mock_watcher.is_running = False
            MockWatcher.return_value = mock_watcher

            watcher = SkillsFileWatcher()
            watcher.start()

            assert watcher._subscribed is True
            MockWatcher.assert_called_once()
            assert mock_watcher.start.called

    @pytest.mark.asyncio
    async def test_start_when_already_running_does_nothing(self):
        """start() called twice → second call is no-op."""
        with patch(
            "app.core.learning.skill_file_watcher.FileWatcher"
        ) as MockWatcher:
            mock_watcher = MagicMock()
            mock_watcher.is_running = True
            MockWatcher.return_value = mock_watcher

            watcher = SkillsFileWatcher()
            watcher.start()  # first — creates watcher
            MockWatcher.reset_mock()

            watcher.start()  # second — already running
            MockWatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_stops_watcher_and_unsubscribes(self):
        """stop() → FileWatcher stopped, events unsubscribed."""
        with patch(
            "app.core.learning.skill_file_watcher.FileWatcher"
        ) as MockWatcher:
            mock_watcher = MagicMock()
            mock_watcher.is_running = True
            MockWatcher.return_value = mock_watcher

            watcher = SkillsFileWatcher()
            watcher.start()
            assert watcher._subscribed is True

            watcher.stop()
            assert watcher._subscribed is False
            assert mock_watcher.stop.called
            assert watcher._watcher is None
