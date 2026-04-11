"""
Core Event System - Shared Event Type Registry

Registry for cross-domain event types that are used by multiple modules.
Module-specific event types should be defined in their respective modules.
"""

from enum import Enum


class SystemEventType(str, Enum):
    """
    System-wide event types.
    
    These are cross-domain events that multiple modules may be interested in.
    """
    # Lifecycle Events
    APP_STARTED = "system.app_started"
    APP_STOPPING = "system.app_stopping"

    # Error Events
    UNHANDLED_ERROR = "system.unhandled_error"

    # Context Polishing
    # Published by Engine after context hydration. Subscribed by Domain experts to enrich/clean context.
    CONTEXT_POLISHING = "system.context_polishing"


# Note: Module-specific event types are defined in their respective modules:
# - AgentEventType -> app.core.engine.events
# - MacroEventType -> app.core.execution.macro.events
# - RewindEventType -> app.core.rewind.events
# - AwakeningEventType -> app.core.environment.events
# - ProjectEventType -> app.domain.project.events
# - IndexingEventType -> app.domain.codebase.events
# - FileSystemEventType -> app.core.file.events
