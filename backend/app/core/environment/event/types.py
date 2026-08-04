"""
Environment Event Types
=======================

Event type constants for the Awakening/Environment domain.
"""

from enum import Enum


class EventType(str, Enum):
    """
    Event types for the Awakening/Environment domain.

    .. note::
        ``system.*`` events (``awakening_complete``, ``state_refreshed``,
        ``boundary_learned``) are defined in :class:`SystemEventType`
        in ``app.core.events.registry`` to maintain single source of truth.
    """

    # Device Events
    DEVICE_CONNECTED = "environment.device_connected"
    DEVICE_DISCONNECTED = "environment.device_disconnected"

    # Capability & Skill Evolution
    SKILL_EXECUTED = "skill.executed"
    SKILL_PROMOTED = "skill.promoted"
    SKILL_DEPRECATED = "skill.deprecated"

    # Perception
    UI_TREE_OBSERVED = "ui.tree_observed"
