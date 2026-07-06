"""
Todo Event Schemas
==================

Pydantic data classes for todo domain events.
"""

from app.core.events.base import BaseEvent

from .types import TodoEventType


class TodoUpdatedEvent(BaseEvent):
    """
    Public event published when todo items are created, updated, or deleted.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = TodoEventType.UPDATED
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
