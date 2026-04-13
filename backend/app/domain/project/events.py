"""
Project Domain Events

Events related to project lifecycle and synchronization.
These events enable decoupling between ProjectSyncService and IndexingManager.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import Field

from app.core.events.base import BaseEvent


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


class ProjectEvent(BaseEvent):
    """Base class for project domain events."""
    event_type: ProjectEventType = ProjectEventType.PROJECT_CREATED
    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = "project"
    data: dict[str, Any] = Field(default_factory=dict)


class ProjectCreatedEvent(ProjectEvent):
    """
    Published when a new project directory is detected.

    Subscribers (e.g., IndexingManager) can react to start indexing.
    """
    path: str = ""
    repo_id: int = 0
    project_id: int | None = None
    project_name: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_CREATED
        self.data = {
            "path": self.path,
            "repo_id": self.repo_id,
            "project_id": self.project_id,
            "project_name": self.project_name
        }


class ProjectDeletedEvent(ProjectEvent):
    """
    Published when a project directory is deleted.

    Subscribers can react to stop watching and cleanup resources.
    """
    path: str = ""
    repo_id: int = 0
    project_id: int | None = None

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_DELETED
        self.data = {
            "path": self.path,
            "repo_id": self.repo_id,
            "project_id": self.project_id
        }


class ProjectMovedEvent(ProjectEvent):
    """
    Published when a project directory is moved/renamed.
    """
    src_path: str = ""
    dest_path: str = ""
    repo_id: int = 0
    new_name: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_MOVED
        self.data = {
            "src_path": self.src_path,
            "dest_path": self.dest_path,
            "repo_id": self.repo_id,
            "new_name": self.new_name
        }


class ProjectSwitchedEvent(ProjectEvent):
    """
    Published when user switches active project context.
    """
    project_id: int = 0
    project_name: str = ""
    path: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_SWITCHED
        self.data = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "path": self.path
        }


class NewProjectDetectedEvent(ProjectEvent):
    """
    Published when a new project directory is detected but not yet imported.

    This event is used to notify the frontend to show a confirmation dialog.
    Importing/indexing should NOT start until user confirms.
    """
    repo_id: int = 0
    path: str = ""
    name: str = ""
    detected_at: datetime = Field(default_factory=datetime.now)

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.NEW_PROJECT_DETECTED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
            "name": self.name,
            "detected_at": self.detected_at.isoformat()
        }
