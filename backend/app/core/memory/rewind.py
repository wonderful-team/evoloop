"""
Memory Rewind Event Schema
==========================

Defines the memory cleanup event schema for conversation rewind operations.

Domain-specific cleanup handlers live in ``event/subscribers.py``.
"""

import logging

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType

logger = logging.getLogger(__name__)


class MemoryCleanupEvent(RewindEvent):
    """Published to trigger memory deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.MEMORY_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "run_ids": self.run_ids,
        }
