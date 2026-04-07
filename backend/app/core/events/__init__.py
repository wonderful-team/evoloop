"""
Core Event System

Provides the foundational event-driven infrastructure for the entire system.

Note: Module-specific events should be imported directly from their modules:
  - from app.core.engine.events import AgentEventType, AgentRunCompletedEvent
  - from app.core.rewind.events import RewindEventType, RewindRequestedEvent
  - from app.core.execution.macro.events import MacroEventType
  - from app.core.environment.events import AwakeningEventType
  - from app.domain.project.events import ProjectEventType
  - from app.domain.codebase.events import IndexingEventType
  - from app.core.file.events import FileSystemEventType
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
