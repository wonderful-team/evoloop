"""
Agent Engine Event Schemas
==========================

Pydantic data classes for agent-related events.
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.constants import DEFAULT_PROJECT_ID
from app.core.events.base import BaseEvent, EventData
from app.core.events.registry import SystemEventType


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
        self.data = EventData(
            thread_id=self.thread_id,
            project_id=self.project_id,
        )


class AgentRunCompletedEvent(AgentEvent):
    """Event emitted when an agent run (thread) finishes successfully."""

    event_type: str = "agent.run_completed"
    thread_id: str = ""
    project_id: int = DEFAULT_PROJECT_ID
    goal: str = ""
    status: str = "done"
    source: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    # Governance: Map to frontend RunEndEvent
    is_public: bool = True
    broadcast_channel: str = "chat"

    @model_validator(mode="after")
    def _build_data(self):
        self.data = EventData(
            thread_id=self.thread_id,
            project_id=self.project_id,
            goal=self.goal,
            status=self.status,
        )
        return self


class WebSocketMessageReceivedEvent(AgentEvent):
    """
    Published when EvoCloudWebSocketLink receives ANY canonical envelope from Gateway.

    All business modules subscribe to this single event type and filter by
    ``msg_type`` internally. The transport layer no longer remaps canonical
    types to legacy strings, so ``msg_type`` equals the envelope ``type``
    (e.g. ``command.relay``, ``command.stop``, ``hitl.response``).

    Attributes:
        msg_type: The canonical envelope type.
        payload:  The envelope ``body``.
        raw:      The complete raw envelope as a dict.
    """

    event_type: str = SystemEventType.WEBSOCKET_MESSAGE_RECEIVED
    msg_type: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str = "websocket"


class ConversationDeletedEvent(AgentEvent):
    """
    Published when a conversation is being deleted.

    Each domain module subscribes to clean up its own associated data.
    The producer (REST API or WS handler) is responsible only for
    deleting the Conversation row itself.
    """

    event_type: str = "conversation.deleted"
    thread_id: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData(thread_id=self.thread_id)


class ConversationCreatedEvent(AgentEvent):
    """
    Published when a new interactive conversation is created.

    Bridged to the frontend via the system channel so all clients
    (desktop / mobile) can refresh their conversation lists in real-time
    when a session is started from another device or channel
    (voice, mobile, wecom, web, etc.).
    """

    event_type: str = SystemEventType.CONVERSATION_CREATED
    thread_id: str = ""
    project_id: int = DEFAULT_PROJECT_ID
    member_id: int = 0
    title: str = ""

    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData(
            thread_id=self.thread_id,
            project_id=self.project_id,
            member_id=self.member_id,
            title=self.title,
        )


class ConversationUpdatedEvent(AgentEvent):
    """
    Published when an existing interactive conversation is updated
    (e.g. its ``updated_at`` bumped by a new message).

    ``status``（可选）携带触发的终态（done/cancelled/failed 等），用于让前端
    区分"仅仅是数据变化"与"本轮 run 已完成"（后者驱动未读完成提示）。

    Bridged to the frontend via the system channel so all clients
    (desktop / mobile) can refresh their conversation lists in real-time
    when a session is continued from another device or channel
    (voice, mobile, wecom, web, etc.).
    """

    event_type: str = SystemEventType.CONVERSATION_UPDATED
    thread_id: str = ""
    project_id: int = DEFAULT_PROJECT_ID
    member_id: int = 0
    title: str = ""
    status: str = ""

    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData(
            thread_id=self.thread_id,
            project_id=self.project_id,
            member_id=self.member_id,
            title=self.title,
            status=self.status,
        )


class ExtractionRequest(BaseModel):
    name: str
    description: str
    schema_dict: dict = Field(
        ...,
        description="The pydantic output_schema as a dict, or raw json schema dict"
    )


class ExtractionRequestedEvent(BaseEvent):
    """Event published to gather schemas from domains before running extraction LLM."""

    event_type: str = SystemEventType.EXTRACTION_REQUESTED
    requests: list[ExtractionRequest] = Field(default_factory=list)
    thread_id: str
    is_public: bool = False


class ExtractionCompletedEvent(BaseEvent):
    """Event published by background worker after LLM structured extraction finishes."""

    event_type: str = SystemEventType.EXTRACTION_COMPLETED
    thread_id: str
    run_id: str | None = None
    project_id: int | None = None
    member_id: int | None = None
    extracted_data: dict = Field(
        default_factory=dict,
        description="The raw structured output from LLM"
    )
    is_public: bool = False
