"""
Environment Event Schemas
=========================

Pydantic data classes for environment/awakening events.
"""

from typing import Any

from pydantic import Field

from app.core.events.registry import SystemEventType
from app.infrastructure.pydantic_base import DynamicBaseModel
from .types import EventType


class AwakenEvent(DynamicBaseModel):
    """Generic event for the awakening domain."""
    event_type: SystemEventType
    data: dict[str, Any] = Field(default_factory=dict)


class DeviceConnectedEvent(DynamicBaseModel):
    """Triggered when a new device is connected."""
    event_type: EventType = EventType.DEVICE_CONNECTED
    device_id: str
    device_type: str = "android"


class DeviceDisconnectedEvent(DynamicBaseModel):
    """Triggered when a device is disconnected."""
    event_type: EventType = EventType.DEVICE_DISCONNECTED
    device_id: str


class BoundaryLearnedEvent(DynamicBaseModel):
    """Triggered when a new capability boundary is learned."""
    event_type: SystemEventType = SystemEventType.BOUNDARY_LEARNED
    tool_name: str
    category: str
    description: str


class UiTreeObservedEvent(DynamicBaseModel):
    """
    Triggered when a UI tree is observed (e.g., via vision or accessibility).
    Consumed by App Atlas for passive learning.
    """
    event_type: EventType = EventType.UI_TREE_OBSERVED
    platform: str
    bundle_id: str
    window_title: str
    elements: list[dict[str, Any]]
    screenshot_hash: str = ""
