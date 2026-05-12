"""
Environment Event Schemas
=========================

Pydantic data classes for environment/awakening events.
"""
from typing import Any
from pydantic import Field

from app.core.events.base import BaseEvent, EventData
from app.core.events.registry import SystemEventType

# Note: We keep a local EventType for internal categorization if needed,
# but it's better to use SystemEventType where possible.
try:
    from app.core.environment.event.types import EventType
except ImportError:
    # Fallback if types not yet moved
    class EventType:
        DEVICE_CONNECTED = "environment.device_connected"
        DEVICE_DISCONNECTED = "environment.device_disconnected"
        UI_TREE_OBSERVED = "environment.ui_tree_observed"


class AwakenEvent(BaseEvent):
    """Generic event for the awakening domain."""
    event_type: str = SystemEventType.AWAKENING_COMPLETE
    
    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "system"


class DeviceConnectedEvent(BaseEvent):
    """Triggered when a new device is connected."""
    event_type: str = EventType.DEVICE_CONNECTED
    device_id: str = ""
    device_type: str = "android"

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData.model_validate({
            "device_id": self.device_id,
            "device_type": self.device_type
        })


class DeviceDisconnectedEvent(BaseEvent):
    """Triggered when a device is disconnected."""
    event_type: str = EventType.DEVICE_DISCONNECTED
    device_id: str = ""

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData.model_validate({
            "device_id": self.device_id
        })


class BoundaryLearnedEvent(BaseEvent):
    """Triggered when a new capability boundary is learned."""
    event_type: str = SystemEventType.BOUNDARY_LEARNED
    tool_name: str = ""
    category: str = ""
    description: str = ""

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = EventData.model_validate({
            "tool_name": self.tool_name,
            "category": self.category,
            "description": self.description
        })


class UiTreeObservedEvent(BaseEvent):
    """
    Triggered when a UI tree is observed.
    """
    event_type: str = EventType.UI_TREE_OBSERVED
    platform: str = ""
    bundle_id: str = ""
    window_title: str = ""
    elements: list[dict[str, Any]] = Field(default_factory=list)
    screenshot_hash: str = ""

    # Usually NOT public (too large)
    is_public: bool = False
