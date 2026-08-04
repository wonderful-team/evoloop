"""
Planning Event Schemas
======================

Pydantic data classes for planning domain events.
"""

from typing import Any

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class PlanUpdatedEvent(BaseEvent):
    """Event published when a plan is created, modified, or deleted."""

    event_type: str = SystemEventType.PLAN_UPDATED
    plan_id: str | None = None
    thread_id: str | None = None
    step_id: str | None = None
    status: str | None = None

    is_public: bool = True
    broadcast_channel: str = "chat"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "plan_id": self.plan_id,
            "thread_id": self.thread_id,
            "step_id": self.step_id,
            "status": self.status,
        }
