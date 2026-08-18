"""
Macro Execution Event Schemas
=============================

Pydantic data classes for macro execution events.
"""

from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType

_EVENT_TYPE_MAP = {
    "create": SystemEventType.MACRO_CREATED,
    "update": SystemEventType.MACRO_UPDATED,
    "delete": SystemEventType.MACRO_DELETED,
    "obsolete": SystemEventType.MACRO_OBSOLETED,
}


class MacroEvent(BaseEvent):
    """Base class for macro-related events."""

    source: str = "macro_engine"


class MacroExecutionFailedEvent(MacroEvent):
    """
    Event emitted when a deterministic macro execution fails.
    Used to trigger perceptual self-healing or reporting.
    """

    event_type: str = "macro.execution_failed"
    skill_id: int | None = None
    skill_name: str | None = None
    error_message: str = ""
    fallback_context: dict | None = None
    thread_id: str = "default"

    # Listeners can append to this to provide guidance back to the agent
    suggestions: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "error_message": self.error_message,
            "fallback_context": self.fallback_context,
            "thread_id": self.thread_id,
        }


class MacroMutatedEvent(MacroEvent):
    """Published when a macro lifecycle event (created/updated/deleted/obsoleted) occurs."""

    source: str = "learning"
    macro_id: int = 0
    action: str = ""
    namespace: str | None = None
    name: str | None = None

    def model_post_init(self, __context: Any) -> None:
        self.event_type = _EVENT_TYPE_MAP.get(self.action) or ""
        self.data = {
            "macro_id": self.macro_id,
            "action": self.action,
            "namespace": self.namespace,
            "name": self.name,
        }
