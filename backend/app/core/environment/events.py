"""
Awakening Event System
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.core.events.base import AsyncEventBus, BaseEvent

logger = logging.getLogger(__name__)


class AwakeningEventType(str, Enum):
    """
    Awakening System event types.
    
    Events related to agent awareness and environment state.
    """
    # Device Events
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"

    # Network Events
    NETWORK_ONLINE = "network.online"
    NETWORK_OFFLINE = "network.offline"

    # Memory Events
    CONCEPT_LEARNED = "memory.concept_learned"
    EPISODE_COMPLETED = "memory.episode_completed"

    # Skill Events
    SKILL_EXECUTED = "skill.executed"
    SKILL_PROMOTED = "skill.promoted"
    SKILL_DEPRECATED = "skill.deprecated"

    # App Events
    APP_LAUNCHED = "app.launched"
    APP_PROBED = "app.probed"
    UI_TREE_OBSERVED = "app.ui_tree_observed"

    # System Events
    AWAKENING_COMPLETE = "system.awakening_complete"
    STATE_REFRESHED = "system.state_refreshed"
    BOUNDARY_LEARNED = "system.boundary_learned"


@dataclass
class AwakenEvent(BaseEvent):
    """Base event class for awakening system"""
    event_type: AwakeningEventType = field(default=AwakeningEventType.AWAKENING_COMPLETE)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "awakening"
    data: dict[str, Any] = field(default_factory=dict)


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
    version_hash: str = ""

    def __post_init__(self):
        self.event_type = AwakeningEventType.UI_TREE_OBSERVED
        self.data = {
            "platform": self.platform,
            "bundle_id": self.bundle_id,
            "window_title": self.window_title,
            # We don't store full elements in the data dict for performance logging reasons,
            # but they remain available on the event object for the subscriber to process.
            "screenshot_hash": self.screenshot_hash,
            "version_hash": self.version_hash
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


# Backward compatibility alias
EventType = AwakeningEventType

# Singleton instance
event_bus = AwakenEventBus()


# =============================================================================
# System Event Handlers (Lifecycle Management)
# =============================================================================

async def _on_app_started(event):
    """Handle APP_STARTED event - start device watcher."""
    from app.core.environment.controllers.device_watcher import device_watcher
    try:
        device_watcher.start()
        logger.info("[Environment] Device watcher started via APP_STARTED event")
    except Exception as e:
        logger.warning(f"[Environment] Failed to start device watcher: {e}")


async def _on_app_stopping(event):
    """Handle APP_STOPPING event - stop device watcher."""
    from app.core.environment.controllers.device_watcher import device_watcher
    try:
        device_watcher.stop()
        logger.info("[Environment] Device watcher stopped via APP_STOPPING event")
    except Exception as e:
        logger.warning(f"[Environment] Failed to stop device watcher: {e}")


def register_environment_system_handlers():
    """
    Register environment module handlers for system lifecycle events.
    
    This should be called during application startup to enable:
    - Auto-start device watcher when app starts
    - Graceful shutdown when app stops
    """
    from app.core.events import system_bus, SystemEventType
    system_bus.subscribe(SystemEventType.APP_STARTED, _on_app_started)
    system_bus.subscribe(SystemEventType.APP_STOPPING, _on_app_stopping)
    logger.info("[Environment] System lifecycle handlers registered")
