"""
Monitoring Event Schemas
========================

Pydantic data classes for monitoring and telemetry events.
"""

from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class SystemStatusEvent(BaseEvent):
    """Event representing a high-level system status change (idle, running, etc)."""

    event_type: str = SystemEventType.STATE_REFRESHED
    status: str = "idle"
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"


class SystemLogEvent(BaseEvent):
    """Event representing a system log entry shared with the UI."""

    event_type: str = SystemEventType.SYSTEM_LOG_ENTRY
    log_type: str = ""
    log_data: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"


class ActivityStateRefreshedEvent(BaseEvent):
    """Event representing a full refresh/update of the agent activity state."""

    event_type: str = SystemEventType.ACTIVITY_STATE_REFRESHED
    activity_state: dict[str, Any] = Field(default_factory=dict)
    thread_id: str

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"
