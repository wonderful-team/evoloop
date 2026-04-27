"""
Project Event Package
=====================

Public exports for project domain event types, schemas, and subscribers.
"""

from .schemas import (
    NewProjectDetectedEvent,
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectEvent,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
    ProjectSwitchEvent,
)
from .types import ProjectEventType

__all__ = [
    "NewProjectDetectedEvent",
    "ProjectCreatedEvent",
    "ProjectDeletedEvent",
    "ProjectEvent",
    "ProjectEventType",
    "ProjectMovedEvent",
    "ProjectSwitchedEvent",
    "ProjectSwitchEvent",
]
