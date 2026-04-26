"""
Project Event Handlers
"""
import logging

from app.core.context import thread_context_store
from app.core.engine.events import WebSocketMessageReceivedEvent
from app.core.events import system_bus
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.domain.project.events import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectEventType,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
    ProjectSwitchEvent,
)
from app.domain.project.sync_service import ProjectSyncService

logger = logging.getLogger(__name__)


@event_register()
class ProjectSwitchWebSocketHandler:
    """
    Handles ``project_switch`` messages from the WebSocket transport layer.

    This class bridges the WebSocket generic event (``WebSocketMessageReceivedEvent``)
    to the domain-specific ``ProjectSwitchedEvent``.  The transport layer does NOT
    know about domain events — it only publishes a generic message-received event.
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "project_switch":
            return

        try:
            switch_data = ProjectSwitchEvent.model_validate(event.payload)
        except Exception as e:
            logger.error(f"[ProjectSwitchWS] Invalid project_switch payload: {e}")
            return

        await system_bus.publish(
            ProjectSwitchedEvent(
                project_id=switch_data.project_id or 0,
                project_name=switch_data.project_name or "",
                path=switch_data.external_path or switch_data.path or "",
            )
        )
        logger.info(
            f"[ProjectSwitchWS] Bridged project_switch -> ProjectSwitchedEvent: "
            f"id={switch_data.project_id}, path={switch_data.external_path or switch_data.path}"
        )


@event_register()
class ProjectDomainHandler:
    """
    Handles domain-specific project events (Created, Deleted, Moved, Switched).
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

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event) -> None:
        """Sync current cloud project to local workspace on app start."""
        try:
            await self._sync_service.sync_cloud_project()
        except Exception as e:
            logger.error(f"[ProjectHandlers] Failed to sync cloud project on start: {e}")

    @event_subscribe(ProjectEventType.PROJECT_SWITCHED)
    async def on_project_switched(self, event: ProjectSwitchedEvent) -> None:
        """
        Handle project switch from WebSocket.

        Updates thread_context_store working directory and active project.
        Other modules (indexing, UI) subscribe to the same ProjectSwitchedEvent
        directly — no need to re-publish a duplicate event.
        """
        project_id = event.project_id
        project_name = event.project_name
        path = event.path

        if path:
            logger.info(f"[ProjectHandlers] Switching project: {project_id} ({project_name}) -> {path}")

            thread_context_store.set_working_directory("remote-default", path)
            thread_context_store.set_working_directory("default", path)

            if project_id:
                thread_context_store.set_active_project("remote-default", project_id)
                thread_context_store.set_active_project("default", project_id)
        else:
            logger.warning(f"[ProjectHandlers] Project switch received but no path provided: {event.model_dump()}")
