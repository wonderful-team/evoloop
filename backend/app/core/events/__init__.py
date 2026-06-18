"""
Core Event System

Provides the foundational event-driven infrastructure for the entire system.

Note: Module-specific events should be imported directly from their modules:
  - from app.core.engine.event.types import AgentEventType
  - from app.core.engine.event.schemas import AgentRunCompletedEvent
  - from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
  - from app.core.execution.macro.event import MacroEventType
  - from app.core.environment.event.types import EventType as AwakeningEventType
  - from app.core.project.event import ProjectEventType
  - from app.domain.codebase.event import IndexingEventType
  - from app.core.file.event import FileSystemEventType
"""

# Import base classes first (no dependencies on other app modules)
from app.core.events.base import (
    AsyncEventBus,
    BaseEvent,
    EventHandler,
    SystemEventBus,
    system_bus,
)

# Import shared event types (defined in registry, no external deps)
from app.core.events.registry import SystemEventType

__all__ = [
    # Base classes
    "BaseEvent",
    "AsyncEventBus",
    "SystemEventBus",
    "EventHandler",
    # Global instance
    "system_bus",
    # Shared event types
    "SystemEventType",
]
