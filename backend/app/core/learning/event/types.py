"""
Learning Event Types
====================

Event type constants for learning domain events.

.. note::
    ``rewind.*_cleanup`` events are defined in :class:`RewindEventType`
    in ``app.core.engine.rewind.event.types`` to maintain single source of truth.
"""

from enum import Enum


class LearningEventType(str, Enum):
    """
    Learning Domain event types.

    Events related to skill synthesis and learning lifecycle.
    """
    SYNTHESIS_COMPLETED = "synthesis.completed"
