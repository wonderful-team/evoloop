"""
Project Event Handlers
"""
import logging

from app.core.events.decorators import event_register, event_subscribe
from app.domain.project.events import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectEventType,
    ProjectMovedEvent,
)
from app.domain.project.sync_service import ProjectSyncService

logger = logging.getLogger(__name__)


@event_register()
class ProjectDomainHandler:
    """
    Handles domain-specific project events (Created, Deleted, Moved).
    """

    def __init__(self):
        self._sync_service = ProjectSyncService()

    @event_subscribe(ProjectEventType.PROJECT_CREATED)
    async def on_project_created(self, event: ProjectCreatedEvent) -> None:
        """Handle project creation."""
        try:
            await self._sync_service.handle_project_created(event.path)
        except Exception as e:
            logger.error(f"[ProjectHandlers] Failed to handle project created: {e}")

    @event_subscribe(ProjectEventType.PROJECT_DELETED)
    async def on_project_deleted(self, event: ProjectDeletedEvent) -> None:
        """Handle project deletion."""
        try:
            await self._sync_service.handle_project_deleted(event.path)
        except Exception as e:
            logger.error(f"[ProjectHandlers] Failed to handle project deleted: {e}")

    @event_subscribe(ProjectEventType.PROJECT_MOVED)
    async def on_project_moved(self, event: ProjectMovedEvent) -> None:
        """Handle project moved."""
        try:
            await self._sync_service.handle_project_moved(event.src_path, event.dest_path)
        except Exception as e:
            logger.error(f"[ProjectHandlers] Failed to handle project moved: {e}")
