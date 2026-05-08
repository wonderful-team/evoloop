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

    # Context Polishing
    # Published by Engine after context hydration. Subscribed by Domain experts to enrich/clean context.
    CONTEXT_POLISHING = "system.context_polishing"

    # Engine Lifecycle
    SESSION_STARTED = "system.session_started"
    SESSION_COMPLETED = "system.session_completed"

    # Configuration Handlers
    CONFIG_CHANGED = "system.config_changed"

    # Awakening / Environment Events
    AWAKENING_COMPLETE = "system.awakening_complete"
    STATE_REFRESHED = "system.state_refreshed"
    BOUNDARY_LEARNED = "system.boundary_learned"

    # Authentication Events
    USER_LOGGED_IN = "system.user_logged_in"
    USER_LOGGED_OUT = "system.user_logged_out"


# Note: Module-specific event types are defined in their respective modules:
# - AgentEventType -> app.core.engine.event.types
# - MacroEventType -> app.core.execution.macro.event.types
# - RewindEventType -> app.core.engine.rewind.event.types
# - Environment EventType -> app.core.environment.event.types
# - ProjectEventType -> app.domain.project.event.types
# - IndexingEventType -> app.domain.codebase.event.types
# - FileSystemEventType -> app.core.file.event.types
