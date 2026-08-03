"""
Project Domain Event Schemas
============================

Pydantic data classes for project lifecycle events.
"""

from typing import Any

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.events.base import BaseEvent

try:
    from app.core.project.event.types import ProjectEventType
except ImportError:

    class ProjectEventType:
        PROJECT_CREATED = "project.created"
        PROJECT_DELETED = "project.deleted"
        PROJECT_MOVED = "project.moved"
        PROJECT_SWITCHED = "project.switched"


class ProjectEvent(BaseEvent):
    """Base class for project domain events."""

    event_type: str = ProjectEventType.PROJECT_CREATED
    source: str = "project"
    data: dict[str, Any] = Field(default_factory=dict)

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "system"


class ProjectCreatedEvent(ProjectEvent):
    """
    Published when a new project directory is detected.
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
            "project_name": self.project_name,
        }


class ProjectDeletedEvent(ProjectEvent):
    """
    Published when a project directory is deleted.
    """

    path: str = ""
    repo_id: int = 0
    project_id: int | None = None

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_DELETED
        self.data = {
            "path": self.path,
            "repo_id": self.repo_id,
            "project_id": self.project_id,
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
            "new_name": self.new_name,
        }


class ProjectSwitchedEvent(ProjectEvent):
    """
    Published when user switches active project context.
    """

    project_id: int = DEFAULT_PROJECT_ID
    project_name: str = ""
    path: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.event_type = ProjectEventType.PROJECT_SWITCHED
        self.data = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "path": self.path,
        }
