"""
Core Event Schemas - Lifecycle
==============================

Event schemas for system-wide lifecycle and status events.
"""
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.engine.message.native_classes import BaseMessage
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
    source: str | None = None
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
    member_id: int | None = None


class UserLoggedOutEvent(BaseEvent):
    """Event published when a user logs out."""
    event_type: str = SystemEventType.USER_LOGGED_OUT
    is_public: bool = True
    broadcast_channel: str = "system"
    member_id: int | None = None


class SubscriptionChangedEvent(BaseEvent):
    """Event published when a user's subscription or benefits change."""
    event_type: str = SystemEventType.SUBSCRIPTION_CHANGED
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


class ConfigChangedEvent(BaseEvent):
    """Event published when a configuration value changes."""
    event_type: str = SystemEventType.CONFIG_CHANGED
    key: str = ""
    old_value: str = ""
    new_value: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }
