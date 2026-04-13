"""
File System Event Types and Data Structures
============================================

Event types and data classes for file system monitoring and changes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from app.core.events.base import BaseEvent


class FileSystemEventType(str, Enum):
    """
    File System event types.
    
    Events related to file system monitoring and changes.
    """
    FILE_CREATED = "fs.file_created"
    FILE_MODIFIED = "fs.file_modified"
    FILE_DELETED = "fs.file_deleted"
    FILE_MOVED = "fs.file_moved"
    DIRECTORY_CREATED = "fs.dir_created"
    DIRECTORY_DELETED = "fs.dir_deleted"
    WATCHER_STARTED = "fs.watcher_started"
    WATCHER_STOPPED = "fs.watcher_stopped"


class FileWatcherEvent(BaseEvent):
    """
    File system event for the event bus.
    
    This extends BaseEvent and integrates with the core event system.
    """
    # Inherited: event_type, timestamp, source, data
    source: str = "file_watcher"
    
    def model_post_init(self, __context: Any) -> None:
        # Ensure source is set to file_watcher if not explicitly provided
        if not self.source or self.source == "system":
            self.source = "file_watcher"


# Type alias for legacy compatibility
FileEventHandler = Callable[[FileWatcherEvent], None]
