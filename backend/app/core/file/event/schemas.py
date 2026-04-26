"""
File System Event Schemas
=========================

Pydantic data classes for file system events.
"""

from collections.abc import Callable
from typing import Any

from app.core.events.base import BaseEvent


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
