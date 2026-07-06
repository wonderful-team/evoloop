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


FileEventHandler = Callable[[FileWatcherEvent], None]
