"""
Environment Module Event Definitions and Domain Bus
"""
import logging
from enum import Enum
from typing import Any, Dict, List

from pydantic import Field

from app.core.events.base import AsyncEventBus
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Event types for the Awakening/Environment domain."""
    # System Lifecycle
    AWAKENING_COMPLETE = "system.awakening_complete"
    STATE_REFRESHED = "system.state_refreshed"
    BOUNDARY_LEARNED = "system.boundary_learned"
    
    # Device Events
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"

    # Capability & Skill Evolution
    SKILL_EXECUTED = "skill.executed"
    SKILL_PROMOTED = "skill.promoted"
    SKILL_DEPRECATED = "skill.deprecated"

    # Perception
    UI_TREE_OBSERVED = "ui.tree_observed"


class AwakenEvent(DynamicBaseModel):
    """Generic event for the awakening domain."""
    event_type: EventType
    data: Dict[str, Any] = Field(default_factory=dict)


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
    event_type: EventType = EventType.BOUNDARY_LEARNED
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
    elements: List[Dict[str, Any]]
    screenshot_hash: str = ""


# Environment domain-specific event bus
# This bus handles internal environment orchestration (Discovery, Watchers, Atlas)
event_bus = AsyncEventBus("awakening")
