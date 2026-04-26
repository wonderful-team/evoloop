"""
Agent Engine Event Types and Data Structures
=============================================

Event types and data classes for agent execution lifecycle.
"""

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.core.events.base import BaseEvent
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentEventPayload(DynamicBaseModel):
    """Dynamic payload for agent lifecycle events."""


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


class WebSocketEventType(str, Enum):
    """
    WebSocket message events from Gateway.

    Published by EvoCloudWebSocketLink when it receives messages from Gateway.
    Business modules subscribe to these instead of registering callbacks on the link.
    """
    NEW_COMMAND = "websocket.new_command"


class AgentEvent(BaseEvent):
    """Base class for agent-related events."""
    source: str = "agent_engine"


class AgentRunCompletedEvent(AgentEvent):
    """Event emitted when an agent run (thread) finishes successfully."""
    event_type: str = AgentEventType.RUN_COMPLETED
    thread_id: str = ""
    project_id: int = 1
    goal: str = ""
    status: str = "done"
    payload: AgentEventPayload = Field(default_factory=AgentEventPayload)

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "status": self.status,
        }
        return self


class WebSocketCommandEvent(AgentEvent):
    """
    Published when EvoCloudWebSocketLink receives a 'new_command' message from Gateway.

    Subscribers (e.g. EngineCommandHandler) receive the raw command payload and
    are responsible for dispatching agent runs or HITL responses.
    """
    event_type: str = WebSocketEventType.NEW_COMMAND
    command: dict[str, Any] = Field(default_factory=dict)
    source: str = "websocket"


class WebSocketMessageReceivedEvent(AgentEvent):
    """
    Published when EvoCloudWebSocketLink receives ANY message from Gateway.

    All business modules subscribe to this single event type and filter by
    ``msg_type`` internally. This eliminates the need for if/elif chains in
    the transport layer and decouples the link from domain logic.

    Attributes:
        msg_type: The Gateway message type (init, new_command, project_switch, query, ...)
        payload:  The ``data`` field from the raw message
        raw:      The complete raw JSON message
    """
    event_type: str = "websocket.message_received"
    msg_type: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str = "websocket"
