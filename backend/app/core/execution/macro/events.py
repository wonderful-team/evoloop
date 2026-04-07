"""
Macro Execution Event Types
===========================

Event types and data structures for macro execution.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from app.core.events.base import BaseEvent


class MacroEventType(str, Enum):
    """
    Macro Execution event types.
    """
    EXECUTION_FAILED = "macro.execution_failed"


@dataclass
class MacroEvent(BaseEvent):
    """Base class for macro-related events."""
    source: str = "macro_engine"


@dataclass
class MacroExecutionFailedEvent(MacroEvent):
    """
    Event emitted when a deterministic macro execution fails.
    Used to trigger perceptual self-healing or reporting.
    """
    skill_id: Optional[int] = None
    skill_name: Optional[str] = None
    error_message: str = ""
    fallback_context: Optional[dict] = None
    thread_id: str = "default"
    
    # Listeners can append to this to provide guidance back to the agent
    suggestions: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.event_type = MacroEventType.EXECUTION_FAILED
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "error_message": self.error_message,
            "fallback_context": self.fallback_context,
            "thread_id": self.thread_id
        }
