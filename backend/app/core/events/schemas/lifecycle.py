"""
Core Event Schemas - Lifecycle
==============================

Event schemas for system-wide lifecycle and status events.
"""
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, model_validator

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class SessionCompletedData(BaseModel):
    """Payload data for SESSION_COMPLETED event."""
    thread_id: str
    run_id: str | None = None
    project_id: int | None = None
    member_id: int | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    blackboard_dict: dict = Field(default_factory=dict, description="Serialized blackboard state")
    summary: str | None = None
    outcome: str | None = None
    audit_tier: str | None = None
    duration_ms: float = 0.0
    # Extra context for learning and domain modules
    model: str | None = None
    original_skill_id: Any | None = None
    ticket_topic: str | None = None
    ticket_reason: str | None = None


class SessionCompletedEvent(BaseEvent):
    """Event published when an agent session reaches a successful conclusion."""
    event_type: str = SystemEventType.SESSION_COMPLETED
    data: SessionCompletedData

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    @model_validator(mode="after")
    def sync_metadata(self) -> "SessionCompletedEvent":
        """Link internal thread_id for routing."""
        if self.data and hasattr(self.data, "thread_id"):
            self.thread_id = self.data.thread_id
        return self

    def to_frontend_payload(self) -> dict:
        """Map to legacy session_completed format."""
        return {
            "type": "session_completed",
            "thread_id": self.thread_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data.model_dump(exclude={"messages", "blackboard_dict"})
        }


class ExtractionRequest(BaseModel):
    name: str
    description: str
    schema_dict: dict = Field(..., description="The pydantic output_schema as a dict, or raw json schema dict")


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
    extracted_data: dict = Field(default_factory=dict, description="The raw structured output from LLM")
    is_public: bool = False


class SystemStatusEvent(BaseEvent):
    """Event representing a high-level system status change (idle, running, etc)."""
    event_type: str = SystemEventType.STATE_REFRESHED
    status: str = "idle"
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    def to_frontend_payload(self) -> dict:
        """Map to legacy StatusEvent format."""
        return {
            "type": "status",
            "thread_id": self.thread_id,
            "status": self.status
        }


class AppStartedEvent(BaseEvent):
    """Event published when the application starts."""
    event_type: str = SystemEventType.APP_STARTED
    is_public: bool = True
    broadcast_channel: str = "system"


class AppStoppingEvent(BaseEvent):
    """Event published when the application is stopping."""
    event_type: str = SystemEventType.APP_STOPPING
    is_public: bool = True
    broadcast_channel: str = "system"


class UserLoggedInEvent(BaseEvent):
    """Event published when a user logs in."""
    event_type: str = SystemEventType.USER_LOGGED_IN
    is_public: bool = True
    broadcast_channel: str = "system"


class UserLoggedOutEvent(BaseEvent):
    """Event published when a user logs out."""
    event_type: str = SystemEventType.USER_LOGGED_OUT
    is_public: bool = True
    broadcast_channel: str = "system"


class SubscriptionChangedEvent(BaseEvent):
    """Event published when a user's subscription or benefits change."""
    event_type: str = "subscription.changed"
    source: str = "subscription"
    member_id: int | None = None
    event: str | None = None  # e.g. subscription_created, subscription_renewed
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "member_id": self.member_id,
            "event": self.event,
        }


class SystemLogEvent(BaseEvent):
    """Event representing a system log entry shared with the UI."""
    event_type: str = "system.log_entry"
    log_type: str = ""
    log_data: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    def to_frontend_payload(self) -> dict:
        """Map to legacy system_log format."""
        return {
            "type": "system_log",
            "event": self.log_type,
            "data": self.log_data,
            "timestamp": self.timestamp.isoformat()
        }
