"""
Core Event System

Provides the foundational event-driven infrastructure for the entire system.
"""

from app.core.events.base import (
    AsyncEventBus,
    BaseEvent,
    EventHandler,
    SystemEventBus,
    system_bus,
)
from app.core.events.registry import (
    AgentEventType,
    AwakeningEventType,
    FileSystemEventType,
    IndexingEventType,
    ProjectEventType,
    SystemEventType,
    MacroEventType,
)

__all__ = [
    # Base classes
    "BaseEvent",
    "AsyncEventBus",
    "SystemEventBus",
    "EventHandler",
    # Macro events
    "MacroEventType",
    # Global instance
    "system_bus",
    # Event types
    "SystemEventType",
    "AwakeningEventType",
    "ProjectEventType",
    "IndexingEventType",
    "AgentEventType",
    "MacroEventType",
    "FileSystemEventType",
]
