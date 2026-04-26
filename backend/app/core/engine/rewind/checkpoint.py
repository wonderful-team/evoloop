"""
Checkpoint Rewind Handler
=========================

Defines the checkpoint cleanup event schema for conversation rewind operations.

Domain-specific cleanup handlers live in ``event/subscribers.py``.
"""

import logging

from pydantic import Field, model_validator

from app.core.engine.rewind.event import RewindEvent, RewindEventType

logger = logging.getLogger(__name__)


class CheckpointCleanupEvent(RewindEvent):
    """Published to trigger checkpoint deletion from SQLite."""
    event_type: str = RewindEventType.CHECKPOINT_CLEANUP
    checkpoint_ids: list[str] = Field(default_factory=list)
    min_checkpoint_id: str | None = None

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "checkpoint_ids": self.checkpoint_ids,
            "min_checkpoint_id": self.min_checkpoint_id,
            "count": len(self.checkpoint_ids),
        }
        return self
