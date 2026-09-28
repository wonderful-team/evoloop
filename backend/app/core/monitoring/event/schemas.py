"""
Monitoring Event Schemas
========================

Pydantic data classes for monitoring and telemetry events.
"""

from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType
from app.core.monitoring.constants import ActivityStatus


class SystemStatusEvent(BaseEvent):
    """Event representing a high-level system status change (idle, running, etc)."""

    event_type: str = SystemEventType.STATE_REFRESHED
    status: ActivityStatus = ActivityStatus.IDLE
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
