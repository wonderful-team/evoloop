"""
Rewind Message Event Schema
===========================

Defines the message cleanup event schema for conversation rewind operations.

Domain-specific cleanup handlers live in ``event/subscribers.py``.
"""

import logging

from pydantic import Field, model_validator

from app.core.engine.rewind.event import RewindEvent, RewindEventType

logger = logging.getLogger(__name__)


class MessagesCleanupEvent(RewindEvent):
    """Published to trigger message deletion."""
    event_type: str = RewindEventType.MESSAGES_CLEANUP
    message_ids: list[str] = Field(default_factory=list)
    delete_references: bool = True

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "message_ids": self.message_ids,
            "count": len(self.message_ids),
        }
        return self
