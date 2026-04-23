"""
Codebase Event Handlers
=======================

Event-driven handlers for codebase/indexing operations.
These handlers receive events from the file watcher and dispatch indexing
operations to the background task queue (Huey/Celery).

Usage:
    Handlers are auto-registered via @event_register decorator.
    They subscribe to IndexingEventType events and enqueue tasks.
"""

import logging

from app.core.events.decorators import event_register, event_subscribe
from app.domain.codebase.events import (
    FileModifiedEvent,
    FileMovedEvent,
    FileRemovedEvent,
    IndexingEventType,
)
from app.infrastructure.queue.factory import get_scheduler

logger = logging.getLogger(__name__)

_scheduler = get_scheduler()


@event_register()
class FileIndexingHandler:
    """
    Handles file indexing events from the file watcher.

    Instead of executing indexing inline (which blocks the main process),
    we dispatch lightweight background tasks to the task queue.
    """

    @event_subscribe(IndexingEventType.FILE_MODIFIED)
    async def on_file_modified(self, event: FileModifiedEvent) -> None:
        """Enqueue a background task to index the modified file."""
        try:
            logger.info(
                f"[FileIndexingHandler] Enqueuing index task for: {event.file_path}"
            )
            _scheduler.send_task(
                "codebase_index_file",
                kwargs={"file_path": event.file_path, "repo_id": event.repo_id},
            )
        except Exception as e:
            logger.error(
                f"[FileIndexingHandler] Failed to enqueue index task for {event.file_path}: {e}"
            )

    @event_subscribe(IndexingEventType.FILE_REMOVED)
    async def on_file_removed(self, event: FileRemovedEvent) -> None:
        """Enqueue a background task to remove the file from the index."""
        try:
            logger.info(
                f"[FileIndexingHandler] Enqueuing remove task for: {event.file_path}"
            )
            _scheduler.send_task(
                "codebase_remove_file",
                kwargs={"file_path": event.file_path, "repo_id": event.repo_id},
            )
        except Exception as e:
            logger.error(
                f"[FileIndexingHandler] Failed to enqueue remove task for {event.file_path}: {e}"
            )

    @event_subscribe(IndexingEventType.FILE_MOVED)
    async def on_file_moved(self, event: FileMovedEvent) -> None:
        """Enqueue a background task to move/rename the file in the index."""
        try:
            logger.info(
                f"[FileIndexingHandler] Enqueuing move task: {event.src_path} -> {event.dest_path}"
            )
            _scheduler.send_task(
                "codebase_move_file",
                kwargs={
                    "src_path": event.src_path,
                    "dest_path": event.dest_path,
                    "repo_id": event.repo_id,
                },
            )
        except Exception as e:
            logger.error(
                f"[FileIndexingHandler] Failed to enqueue move task for {event.src_path}: {e}"
            )
