"""
Learning Event Schemas
======================

Pydantic data classes for learning domain events.
"""

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType


class TraceCleanupEvent(RewindEvent):
    """Published to trigger trace event deletion."""
    source_message_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.TRACE_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "count": len(self.source_message_ids),
        }
