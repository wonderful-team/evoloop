"""
Tool Domain Event Schemas
=========================

Pydantic data classes for tool-related events.
"""

from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent, EventData

from .types import ToolEventType


class BackgroundTaskEvent(BaseEvent):
    """Event published when a background task state changes."""

    event_type: str = ToolEventType.BACKGROUND_TASK_UPDATED
    task_id: str = ""
    action: str = "updated"  # created, started, completed, failed, cancelled, timeout
    task_data: dict[str, Any] = Field(default_factory=dict)

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"  # Usually tied to a thread

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData(
            task_id=self.task_id,
            action=self.action,
            task=self.task_data,
        )


class BackgroundTaskOutputEvent(BaseEvent):
    """Event published for real-time task output streaming."""

    event_type: str = ToolEventType.BACKGROUND_TASK_OUTPUT
    task_id: str = ""
    output: str = ""

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"
