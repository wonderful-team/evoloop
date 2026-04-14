"""
Macro Execution Event Types
===========================

Event types and data structures for macro execution.
"""

from enum import Enum
from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent


class MacroEventType(str, Enum):
    """
    Macro Execution event types.
    """
    EXECUTION_FAILED = "macro.execution_failed"


class MacroEvent(BaseEvent):
    """Base class for macro-related events."""
    source: str = "macro_engine"


class MacroExecutionFailedEvent(MacroEvent):
    """
    Event emitted when a deterministic macro execution fails.
    Used to trigger perceptual self-healing or reporting.
    """
    skill_id: int | None = None
    skill_name: str | None = None
    error_message: str = ""
    fallback_context: dict | None = None
    thread_id: str = "default"

    # Listeners can append to this to provide guidance back to the agent
    suggestions: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self.event_type = MacroEventType.EXECUTION_FAILED
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "error_message": self.error_message,
            "fallback_context": self.fallback_context,
            "thread_id": self.thread_id
        }
