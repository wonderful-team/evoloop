"""
Context Event Schemas
=====================

Pydantic data classes for context domain events.
"""
from typing import Any
from pydantic import Field
from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class ContextPolishingEvent(BaseEvent):
    """Event published by Engine after context hydration."""
    event_type: str = SystemEventType.CONTEXT_POLISHING
    thread_id: str | None = None
    project_id: int | None = None
    model: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "model": self.model,
            "context": self.context,
        }
