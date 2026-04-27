"""
Todo Event Schemas
==================

Pydantic data classes for todo-related events.
"""

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType


class TodoCleanupEvent(RewindEvent):
    """Published to trigger todo item deletion."""

    source_message_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.TODO_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "count": len(self.source_message_ids),
        }
