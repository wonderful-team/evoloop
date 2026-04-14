"""
Codebase Event Handlers
=======================

Event-driven handlers for codebase/indexing operations.
These handlers receive events from the file watcher and perform indexing operations.

Usage:
    Handlers are auto-registered via @event_register decorator.
    They subscribe to IndexingEventType events and call IndexingService.
"""

import logging

from app.core.events.decorators import event_register, event_subscribe
from app.domain.codebase.events import (
    FileModifiedEvent,
    FileMovedEvent,
    FileRemovedEvent,
    IndexingEventType,
)
from app.domain.codebase.indexing.service import IndexingService

logger = logging.getLogger(__name__)


@event_register()
class FileIndexingHandler:
    """
    Handles file indexing events from the file watcher.
    
    This handler receives file change events and delegates to IndexingService
    to perform the actual indexing operations.
    """

    def __init__(self):
        self._service = IndexingService()

    @event_subscribe(IndexingEventType.FILE_MODIFIED)
    async def on_file_modified(self, event: FileModifiedEvent) -> None:
        """
        Handle file modification event.
        
        Called when a file is created or modified in a watched directory.
        """
        try:
            logger.info(f"[FileIndexingHandler] Indexing modified file: {event.file_path}")
            await self._service.index_file(event.file_path, event.repo_id)
        except Exception as e:
            logger.error(f"[FileIndexingHandler] Failed to index file {event.file_path}: {e}")

    @event_subscribe(IndexingEventType.FILE_REMOVED)
    async def on_file_removed(self, event: FileRemovedEvent) -> None:
        """
        Handle file removal event.
        
        Called when a file is deleted from a watched directory.
        """
        try:
            logger.info(f"[FileIndexingHandler] Removing file from index: {event.file_path}")
            await self._service.remove_file(event.file_path, event.repo_id)
        except Exception as e:
            logger.error(f"[FileIndexingHandler] Failed to remove file {event.file_path}: {e}")

    @event_subscribe(IndexingEventType.FILE_MOVED)
    async def on_file_moved(self, event: FileMovedEvent) -> None:
        """
        Handle file move/rename event.
        
        Called when a file is moved or renamed in a watched directory.
        """
        try:
            logger.info(f"[FileIndexingHandler] Moving file in index: {event.src_path} -> {event.dest_path}")
            await self._service.move_file(event.src_path, event.dest_path, event.repo_id)
        except Exception as e:
            logger.error(f"[FileIndexingHandler] Failed to move file {event.src_path}: {e}")
