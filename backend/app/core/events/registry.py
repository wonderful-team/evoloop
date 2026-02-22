"""
Core Event System - Event Type Registry

Centralized registry for all system event types.
Domain modules should define their event types here for discoverability.
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


class ProjectEventType(str, Enum):
    """
    Project Domain event types.
    
    Events related to project lifecycle and synchronization.
    """
    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    PROJECT_MOVED = "project.moved"
    PROJECT_SYNCED = "project.synced"
    PROJECT_SWITCHED = "project.switched"


class IndexingEventType(str, Enum):
    """
    Indexing Domain event types.
    
    Events related to codebase indexing and file watching.
    """
    INDEXING_STARTED = "indexing.started"
    INDEXING_COMPLETED = "indexing.completed"
    INDEXING_FAILED = "indexing.failed"
    FILE_INDEXED = "indexing.file_indexed"
    FILE_REMOVED = "indexing.file_removed"


class AgentEventType(str, Enum):
    """
    Agent Execution event types.
    
    Events related to agent runs and interactions.
    """
    RUN_STARTED = "agent.run_started"
    RUN_COMPLETED = "agent.run_completed"
    RUN_CANCELLED = "agent.run_cancelled"
    TOOL_EXECUTED = "agent.tool_executed"
    HITL_REQUESTED = "agent.hitl_requested"
    HITL_RESPONDED = "agent.hitl_responded"
