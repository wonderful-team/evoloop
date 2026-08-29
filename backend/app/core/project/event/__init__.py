"""
Project Event Package
======================

Public exports for project domain event types, schemas, and subscribers.
"""

from app.core.project.event.subscribers import (  # noqa: F401 — 导入以触发 @event_register 注册
    ProjectContextHydratorSubscriber,
    ProjectDomainSubscriber,
    ProjectLifecycleSubscriber,
    ProjectSwitchWebSocketSubscriber,
)

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
