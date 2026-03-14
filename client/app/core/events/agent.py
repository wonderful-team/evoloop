from dataclasses import dataclass, field
from typing import Any
from app.core.events.base import BaseEvent
from app.core.events.registry import AgentEventType


@dataclass
class AgentEvent(BaseEvent):
    """Base class for agent-related events."""
    source: str = "agent_engine"


@dataclass
class AgentRunCompletedEvent(AgentEvent):
    """Event emitted when an agent run (thread) finishes successfully."""
    thread_id: str = ""
    project_id: int = 1
    goal: str = ""
    status: str = "done"
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = AgentEventType.RUN_COMPLETED
        self.data = {
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "status": self.status
        }
