"""
Todo Event Types
================

Event type constants for todo domain events.

.. note::
    ``rewind.todo_cleanup`` is defined in :class:`RewindEventType`
    in ``app.core.engine.rewind.event.types`` to maintain single source of truth.
"""

from enum import Enum


class TodoEventType(str, Enum):
    """
    Todo Domain event types.

    Events related to todo item lifecycle changes.
    """
    UPDATED = "todo.updated"
