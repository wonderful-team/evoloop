"""
File System Event Schemas
=========================

Pydantic data classes for file system events.
"""

from collections.abc import Callable
from typing import Any

from app.core.events.base import BaseEvent


class FileWatcherEvent(BaseEvent):
    """File system event for the event bus."""
    source: str = "file_watcher"

    def model_post_init(self, __context: Any) -> None:
        if not self.source or self.source == "system":
            self.source = "file_watcher"


class FilesCleanupEvent(BaseEvent):
    """Event representing file reversion cleanup operations."""
    event_type: str = "rewind.files.cleanup"
    thread_id: str = ""
    file_operations: list[dict] = []


class ChangesetUpdatedEvent(BaseEvent):
    """Event published when a changeset (file modification) is updated."""
    event_type: str = "changeset.updated"
    message_id: str | None = None
    file_path: str | None = None
    operation: str | None = None
    thread_id: str | None = None

    is_public: bool = True
    broadcast_channel: str = "chat"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "message_id": self.message_id,
            "file_path": self.file_path,
            "operation": self.operation,
            "thread_id": self.thread_id,
        }


FileEventHandler = Callable[[FileWatcherEvent], None]
