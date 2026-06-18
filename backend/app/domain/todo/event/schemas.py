"""
Todo Event Schemas
==================

Pydantic data classes for todo domain events.
"""

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType
from app.core.events.base import BaseEvent


class TodoCleanupEvent(RewindEvent):
    """Published to trigger todo item deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    affected_run_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.TODO_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "affected_run_ids": self.affected_run_ids,
            "count": len(self.source_message_ids),
        }


class TodoUpdatedEvent(BaseEvent):
    """
    Public event published when todo items are created, updated, or deleted.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = "todo.updated"
    source: str = "todo"
    todo_id: str | None = None
    action: str = "updated"  # created / updated / deleted / completed
    project_id: int | None = None
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context) -> None:
        self.data = {
            "todo_id": self.todo_id,
            "action": self.action,
            "project_id": self.project_id,
        }
