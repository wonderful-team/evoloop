"""
Project Domain Event Types
==========================

Event type constants for project lifecycle and synchronization.
"""

from enum import Enum


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
    NEW_PROJECT_DETECTED = "project.new_detected"
