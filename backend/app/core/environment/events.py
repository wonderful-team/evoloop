"""
Awakening Event System

Defines event types and the central Event Bus for the awakening system.
Now extends the core AsyncEventBus for consistency across the system.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from app.core.events.base import AsyncEventBus, BaseEvent
from app.core.events.registry import AwakeningEventType

logger = logging.getLogger(__name__)


# Re-export EventType for backward compatibility
EventType = AwakeningEventType


@dataclass
class AwakenEvent(BaseEvent):
    """Base event class for awakening system"""
    event_type: AwakeningEventType = field(default=AwakeningEventType.AWAKENING_COMPLETE)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "awakening"
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceConnectedEvent(AwakenEvent):
    """Device connection event"""
    device_id: str = ""
    device_type: str = "android"  # android, macos
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.DEVICE_CONNECTED
        self.data = {"device_id": self.device_id, "device_type": self.device_type}


@dataclass
class DeviceDisconnectedEvent(AwakenEvent):
    """Device disconnection event"""
    device_id: str = ""
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.DEVICE_DISCONNECTED
        self.data = {"device_id": self.device_id}


@dataclass
class SkillExecutedEvent(AwakenEvent):
    """Skill execution result event"""
    skill_id: int = 0
    skill_name: str = ""
    success: bool = True
    confidence_delta: float = 0.0
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.SKILL_EXECUTED
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "success": self.success,
            "confidence_delta": self.confidence_delta
        }


@dataclass
class SkillPromotedEvent(AwakenEvent):
    """Skill promotion event"""
    skill_id: int = 0
    skill_name: str = ""
    old_status: str = ""
    new_status: str = ""
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.SKILL_PROMOTED
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "old_status": self.old_status,
            "new_status": self.new_status
        }


@dataclass
class SkillDeprecatedEvent(AwakenEvent):
    """Skill deprecation event"""
    skill_id: int = 0
    skill_name: str = ""
    reason: str = ""
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.SKILL_DEPRECATED
        self.data = {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "reason": self.reason
        }


@dataclass
class UiTreeObservedEvent(AwakenEvent):
    """Event emitted when a UI tree snapshot is captured by any explorer or tool."""
    platform: str = ""
    bundle_id: str = ""
    window_title: str = ""
    elements: list = field(default_factory=list)
    screenshot_hash: str = ""
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.UI_TREE_OBSERVED
        self.data = {
            "platform": self.platform,
            "bundle_id": self.bundle_id,
            "window_title": self.window_title,
            # We don't store full elements in the data dict for performance logging reasons,
            # but they remain available on the event object for the subscriber to process.
            "screenshot_hash": self.screenshot_hash
        }


@dataclass
class BoundaryLearnedEvent(AwakenEvent):
    """Dynamic boundary learned event"""
    tool_name: str = ""
    category: str = ""
    description: str = ""
    
    def __post_init__(self):
        self.event_type = AwakeningEventType.BOUNDARY_LEARNED
        self.data = {
            "tool_name": self.tool_name,
            "category": self.category,
            "description": self.description
        }


# Type alias for event handlers (backward compatible)
EventHandler = Callable[[AwakenEvent], Awaitable[None]]


class AwakenEventBus(AsyncEventBus[AwakenEvent]):
    """
    Singleton event bus for the awakening system.
    
    Extends the core AsyncEventBus with awakening-specific initialization.
    Maintains backward compatibility with existing code.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            # Initialize parent class
            cls._instance._name = "awakening"
            cls._instance._handlers = {}
            cls._instance._global_handlers = []
            cls._instance._initialized = False
            cls._instance._lock = None  # Will be created when needed
        return cls._instance


# Singleton instance
event_bus = AwakenEventBus()
