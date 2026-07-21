"""
Project Event Package
=====================

Public exports for project domain event types, schemas, and subscribers.
"""

from .schemas import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectEvent,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
)
from .types import ProjectEventType

__all__ = [
    "ProjectCreatedEvent",
    "ProjectDeletedEvent",
    "ProjectEvent",
    "ProjectEventType",
    "ProjectMovedEvent",
    "ProjectSwitchedEvent",
]
