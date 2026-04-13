"""
Agent Engine Event Types and Data Structures
=============================================

Event types and data classes for agent execution lifecycle.
"""

from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field
from app.utils.model_helpers import LegacyDictMixin
from app.core.events.base import BaseEvent


class AgentEventPayload(BaseModel, LegacyDictMixin):
    """Dynamic payload for agent lifecycle events."""
    model_config = ConfigDict(extra="allow")


class AgentEventType(str, Enum):
    """
    Agent Execution event types.
    
    Events related to agent runs and interactions.
    """
    RUN_STARTED = "agent.run_started"
    RUN_COMPLETED = "agent.run_completed"
    RUN_CANCELLED = "agent.run_cancelled"
    TOOL_EXECUTED = "agent.tool_executed"
    HITL_REQUESTED = "agent.hitl_requested"
    HITL_RESPONDED = "agent.hitl_responded"


class AgentEvent(BaseEvent, LegacyDictMixin):
    """Base class for agent-related events."""
    source: str = "agent_engine"


class AgentRunCompletedEvent(AgentEvent):
    """Event emitted when an agent run (thread) finishes successfully."""
    thread_id: str = ""
    project_id: int = 1
    goal: str = ""
    status: str = "done"
    payload: AgentEventPayload = Field(default_factory=AgentEventPayload)

    def model_post_init(self, __context: Any) -> None:
        self.event_type = AgentEventType.RUN_COMPLETED
        self.data = {
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "status": self.status
        }
