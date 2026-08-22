"""
Core Event System - Shared Event Type Registry

Registry for cross-domain event types that are used by multiple modules.
Module-specific event types should be defined in their respective modules.
"""

from enum import Enum

from app.core.events.base import BaseEvent


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
    EXTRACTION_REQUESTED = "system.extraction_requested"
    EXTRACTION_COMPLETED = "system.extraction_completed"
    WEBSOCKET_MESSAGE_RECEIVED = "websocket.message_received"
    # 服务端主动推送的任意 MCP notification（method 与 payload 在 event.data 中）
    MCP_SERVER_NOTIFICATION = "mcp.server_notification"

    # Conversation Lifecycle
    CONVERSATION_CREATED = "conversation.created"

    # Configuration Handlers
    CONFIG_CHANGED = "system.config_changed"
    STATE_CHANGED = "system.state_changed"

    # Awakening / Environment Events
    AWAKENING_COMPLETE = "system.awakening_complete"
    STATE_REFRESHED = "system.state_refreshed"
    ACTIVITY_STATE_REFRESHED = "system.activity_state_refreshed"
    BOUNDARY_LEARNED = "system.boundary_learned"

    # Authentication Events
    USER_LOGGED_IN = "system.user_logged_in"
    USER_LOGGED_OUT = "system.user_logged_out"

    # External Service / Infrastructure Events
    EMBEDDING_UPDATED = "system.embedding_updated"

    # Skill Lifecycle Events
    SKILL_CREATED = "learning.skill_created"
    SKILL_UPDATED = "learning.skill_updated"
    SKILL_DELETED = "learning.skill_deleted"

    # Macro Lifecycle Events
    MACRO_CREATED = "learning.macro_created"
    MACRO_UPDATED = "learning.macro_updated"
    MACRO_DELETED = "learning.macro_deleted"
    MACRO_OBSOLETED = "learning.macro_obsoleted"

    # Subscriptions & Logs
    SUBSCRIPTION_CHANGED = "subscription.changed"
    SYSTEM_LOG_ENTRY = "system.log_entry"
    PLAN_UPDATED = "plan.updated"
    CHANGESET_UPDATED = "changeset.updated"
    ARTIFACT_VALIDATION = "system.artifact_validation"


class ArtifactValidationEvent(BaseEvent):
    """Event triggered to request verification of an artifact's physical database presence."""

    event_type: str = SystemEventType.ARTIFACT_VALIDATION
    project_id: int
    item: str
    is_valid: bool = True


# Note: Module-specific event types are defined in their respective modules:
# - AgentEventType -> app.core.engine.event.types
# - MacroEventType -> app.core.execution.macro.event.types
# - RewindEventType -> app.core.engine.rewind.event.types
# - Environment EventType -> app.core.environment.event.types
# - ProjectEventType -> app.core.project.event.types
# - IndexingEventType -> app.domain.codebase.event.types
# - FileSystemEventType -> app.core.file.event.types
# - ToolEventType -> app.core.tools.event.types
# - TodoEventType -> app.domain.todo.event.types
# - VisionEventType -> app.infrastructure.vision.event.types
