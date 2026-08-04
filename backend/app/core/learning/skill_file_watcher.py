"""
Skills File Watcher — File → DB sync via watchdog

Monitors the ~/.evoloop/skills/ directory for SKILL.md changes
and incrementally syncs them to the LearnedSkill database.
"""

import logging
import os

from app.core.config import settings
from app.core.file.event import FileSystemEventType
from app.core.file.watcher import FileWatcher
from app.core.learning.skill_sync_service import skill_sync_service

logger = logging.getLogger(__name__)

_SKILL_MD = "SKILL.md"


def _is_skill_md(path: str) -> bool:
    """Filter: only accept SKILL.md files."""
    return path.endswith(_SKILL_MD)


def _is_skill_relevant(path: str) -> bool:
    """Watcher filter: SKILL.md files plus extension-less paths (skill
    directories) so DIRECTORY_DELETED for a skill folder still reaches the
    handler while unrelated file noise is dropped early."""
    if path.endswith(_SKILL_MD):
        return True
    return "." not in os.path.basename(path.rstrip(os.sep))


async def _handle_file_created(event):
    """Handle FILE_CREATED events for SKILL.md files."""
    path = event.data.get("path", "")

    if not path.endswith(_SKILL_MD):
        return

    logger.info(f"[Watcher] SKILL.md created: {path}")
    await skill_sync_service.import_skill_from_disk(path)


async def _handle_file_modified(event):
    """Handle FILE_MODIFIED events for SKILL.md files."""
    path = event.data.get("path", "")

    if not path.endswith(_SKILL_MD):
        return
    if not os.path.exists(path):
        return

    logger.info(f"[Watcher] SKILL.md modified: {path}")
    await skill_sync_service.import_skill_from_disk(path)


async def _handle_file_deleted(event):
    """Handle FILE_DELETED events for SKILL.md files."""
    path = event.data.get("path", "")

    if not path.endswith(_SKILL_MD):
        return

    logger.info(f"[Watcher] SKILL.md deleted: {path}")
    await skill_sync_service.delete_skill_by_path(path)


async def _handle_directory_deleted(event):
    """Handle DIRECTORY_DELETED events."""
    path = event.data.get("path", "")

    # Check if this directory could be a skill (has SKILL.md - though it's deleted)
    skill_md_path = os.path.join(path, _SKILL_MD)
    logger.info(f"[Watcher] Directory deleted, checking for skill: {path}")
    await skill_sync_service.delete_skill_by_path(skill_md_path)


class SkillsFileWatcher:
    """
    Watches the skills directory for changes and syncs to DB.

    Started automatically during app startup and stopped during shutdown.
    """

    def __init__(self):
        self._watcher: FileWatcher | None = None
        self._subscribed = False

    def start(self):
        """Start watching the skills directory."""
        skills_dir = settings.SKILLS_DIR
        if not os.path.isdir(skills_dir):
            logger.warning(f"[Watcher] Skills directory does not exist: {skills_dir}")
            return

        if self._watcher and self._watcher.is_running:
            logger.debug("[Watcher] Already watching skills directory")
            return

        self._watcher = FileWatcher(
            path=skills_dir,
            recursive=True,
            debounce_delay=1.0,
            file_filter=_is_skill_relevant,
        )
        self._watcher.start()
        self._subscribe()
        logger.info(f"[Watcher] Started watching: {skills_dir}")

    def stop(self):
        """Stop watching the skills directory."""
        self._unsubscribe()
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
            logger.info("[Watcher] Stopped watching skills directory")

    def _subscribe(self):
        """Subscribe to file system events for skills."""
        from app.core.events import system_bus

        if self._subscribed:
            return

        system_bus.subscribe(FileSystemEventType.FILE_CREATED, _handle_file_created)
        system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, _handle_file_modified)
        system_bus.subscribe(FileSystemEventType.FILE_DELETED, _handle_file_deleted)
        system_bus.subscribe(FileSystemEventType.DIRECTORY_DELETED, _handle_directory_deleted)
        self._subscribed = True

    def _unsubscribe(self):
        """Unsubscribe from file system events."""
        from app.core.events import system_bus

        if not self._subscribed:
            return

        system_bus.unsubscribe(FileSystemEventType.FILE_CREATED, _handle_file_created)
        system_bus.unsubscribe(FileSystemEventType.FILE_MODIFIED, _handle_file_modified)
        system_bus.unsubscribe(FileSystemEventType.FILE_DELETED, _handle_file_deleted)
        system_bus.unsubscribe(FileSystemEventType.DIRECTORY_DELETED, _handle_directory_deleted)
        self._subscribed = False

    @property
    def is_running(self) -> bool:
        return self._watcher is not None and self._watcher.is_running


skills_file_watcher = SkillsFileWatcher()
