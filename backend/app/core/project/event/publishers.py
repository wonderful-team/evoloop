"""
Project Event Publishers
========================

Helper functions for publishing project lifecycle events.
"""

from datetime import datetime

from app.core.events import system_bus
from .schemas import (
    NewProjectDetectedEvent,
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
)


async def publish_new_project_detected(
    repo_id: int, path: str, name: str, detected_at: datetime
) -> None:
    """Publish an event when a new project is detected but not yet imported."""
    await system_bus.publish(
        NewProjectDetectedEvent(
            repo_id=repo_id,
            path=path,
            name=name,
            detected_at=detected_at,
        )
    )


async def publish_project_created(
    path: str, repo_id: int, project_id: int | None, project_name: str
) -> None:
    """Publish an event when a project is created or imported."""
    await system_bus.publish(
        ProjectCreatedEvent(
            path=path,
            repo_id=repo_id,
            project_id=project_id,
            project_name=project_name,
        )
    )


async def publish_project_deleted(
    path: str, repo_id: int, project_id: int | None
) -> None:
    """Publish an event when a project is deleted or disconnected."""
    await system_bus.publish(
        ProjectDeletedEvent(
            path=path,
            repo_id=repo_id,
            project_id=project_id,
        )
    )


async def publish_project_moved(src_path: str, dest_path: str) -> None:
    """Publish an event when a project is moved or renamed."""
    await system_bus.publish(
        ProjectMovedEvent(src_path=src_path, dest_path=dest_path)
    )


async def publish_project_switched(
    project_id: int, project_name: str, path: str
) -> None:
    """Publish an event when user switches active project context."""
    await system_bus.publish(
        ProjectSwitchedEvent(
            project_id=project_id,
            project_name=project_name,
            path=path,
        )
    )
