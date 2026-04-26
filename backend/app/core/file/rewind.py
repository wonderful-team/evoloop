"""
File Rewind Event Schema
========================

Defines the file cleanup event schema for conversation rewind operations.

Domain-specific cleanup handlers live in ``event/subscribers.py``.
"""

import logging

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType

logger = logging.getLogger(__name__)


class FilesCleanupEvent(RewindEvent):
    """Published to trigger file restoration."""
    file_operations: list[dict] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.FILES_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "operation_count": len(self.file_operations),
        }
