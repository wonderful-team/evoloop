"""
Agent Engine Event Schemas
==========================

Pydantic data classes for agent-related events.
"""

from typing import Any

from pydantic import Field, model_validator

from app.core.events.base import BaseEvent, EventData


class AgentEvent(BaseEvent):
    """Base class for agent-related events."""
    source: str = "agent_engine"


class AgentSessionStartedEvent(AgentEvent):
    """Event emitted when an agent session begins, to request context hydration."""
    event_type: str = "system.session_started"
    thread_id: str = ""
    project_id: int | None = None
    
    # Governance: Map to frontend RunStartEvent
    is_public: bool = True
    broadcast_channel: str = "chat"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData.model_validate({
            "thread_id": self.thread_id,
            "project_id": self.project_id
        })

    def to_frontend_payload(self) -> dict:
        """Map to legacy RunStartEvent format."""
        return {
            "type": "run_start",
            "thread_id": self.thread_id,
            "run_id": None, # Session start doesn't have a run_id yet
            "goal": "Initializing session..."
        }


class AgentRunCompletedEvent(AgentEvent):
    """Event emitted when an agent run (thread) finishes successfully."""
    event_type: str = "agent.run_completed"
    thread_id: str = ""
    project_id: int = 1
    goal: str = ""
    status: str = "done"
    payload: dict[str, Any] = Field(default_factory=dict)

    # Governance: Map to frontend RunEndEvent
    is_public: bool = True
    broadcast_channel: str = "chat"

    @model_validator(mode="after")
    def _build_data(self):
        self.data = EventData.model_validate({
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "status": self.status,
        })
        return self

    def to_frontend_payload(self) -> dict:
        """Map to legacy RunEndEvent format."""
        return {
            "type": "run_end",
            "thread_id": self.thread_id,
            "run_id": self.payload.get("run_id"),
            "status": self.status,
            "final_outcome": self.payload.get("outcome") or self.payload.get("summary")
        }


class WebSocketCommandEvent(AgentEvent):
    """
    Published when EvoCloudWebSocketLink receives a 'new_command' message from Gateway.

    Subscribers (e.g. EngineCommandSubscriber) receive the raw command payload and
    are responsible for dispatching agent runs or HITL responses.

    .. deprecated::
        Use ``WebSocketMessageReceivedEvent`` with ``msg_type == "new_command"`` instead.
    """
    event_type: str = "websocket.new_command"
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
