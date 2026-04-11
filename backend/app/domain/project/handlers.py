"""
Project Event Handlers
======================

Event-driven handlers for project lifecycle operations.
These handlers receive events from the file watcher and perform project sync operations.

Usage:
    Handlers are auto-registered via @event_register decorator.
    They subscribe to ProjectEventType events and call ProjectSyncService.
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


def register_project_polisher() -> None:
    """
    Register the ProjectPolisher as a subscriber to SystemEventType.CONTEXT_POLISHING.
    Called during app startup. Wires Domain expertise into the Engine's event stream
    without any Engine-side knowledge of project/codebase domain logic.
    """
    from app.core.events import system_bus
    from app.core.events.registry import SystemEventType
    from app.domain.project.polisher import project_polisher

    system_bus.subscribe(
        SystemEventType.CONTEXT_POLISHING,
        project_polisher.handle_context_polishing,
    )
    logger.info("[ProjectHandlers] ✅ ProjectPolisher subscribed to CONTEXT_POLISHING")


@event_register()
class ProjectSyncHandler:
    """
    Handles project lifecycle events from the file watcher.
    
    This handler receives project change events and delegates to ProjectSyncService
    to perform the actual synchronization operations.
    """

    def __init__(self):
        self._service = ProjectSyncService()

    @event_subscribe(ProjectEventType.PROJECT_CREATED)
    async def on_project_created(self, event: ProjectCreatedEvent) -> None:
        """
        Handle project creation event.
        
        Called when a new project directory is detected in the workspace.
        """
        try:
            logger.info(f"[ProjectSyncHandler] Handling project created: {event.path}")
            await self._service.handle_project_created(event.path)
        except Exception as e:
            logger.error(f"[ProjectSyncHandler] Failed to handle project created {event.path}: {e}")

    @event_subscribe(ProjectEventType.PROJECT_DELETED)
    async def on_project_deleted(self, event: ProjectDeletedEvent) -> None:
        """
        Handle project deletion event.
        
        Called when a project directory is deleted from the workspace.
        """
        try:
            logger.info(f"[ProjectSyncHandler] Handling project deleted: {event.path}")
            await self._service.handle_project_deleted(event.path)
        except Exception as e:
            logger.error(f"[ProjectSyncHandler] Failed to handle project deleted {event.path}: {e}")

    @event_subscribe(ProjectEventType.PROJECT_MOVED)
    async def on_project_moved(self, event: ProjectMovedEvent) -> None:
        """
        Handle project move/rename event.
        
        Called when a project directory is moved or renamed in the workspace.
        """
        try:
            logger.info(f"[ProjectSyncHandler] Handling project moved: {event.src_path} -> {event.dest_path}")
            await self._service.handle_project_moved(event.src_path, event.dest_path)
        except Exception as e:
            logger.error(f"[ProjectSyncHandler] Failed to handle project moved {event.src_path}: {e}")
