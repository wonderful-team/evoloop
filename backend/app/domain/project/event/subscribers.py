"""
Project Event Subscribers
=========================

Event subscribers for project lifecycle, synchronization, and memory context.
"""

import asyncio
import logging
import os

from app.constants import PROJECT_NORM_FILES
from app.core.context import thread_context_store
from app.core.engine.event.schemas import WebSocketMessageReceivedEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.memory.event import MemoryContextGatherEvent
from app.core.memory.event.types import MEMORY_CONTEXT_GATHER_EVENT_TYPE
from app.domain.project.sync_service import ProjectSyncService
from app.infrastructure.config import SystemConfigService
from app.utils import render_template
from .schemas import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
)
from .types import ProjectEventType

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
            switch_data = ProjectSwitchedEvent.model_validate(event.payload)
        except Exception as e:
            logger.error(f"[ProjectSwitchWS] Invalid project_switch payload: {e}")
            return

        from app.domain.project.event.publishers import publish_project_switched
        await publish_project_switched(
            project_id=switch_data.project_id or 0,
            project_name=switch_data.project_name or "",
            path=switch_data.path or "",
        )
        logger.info(
            f"[ProjectSwitchWS] Bridged project_switch -> ProjectSwitchedEvent: "
            f"id={switch_data.project_id}, path={switch_data.path}"
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


@event_register()
class ProjectLifecycleHandler:
    """
    Handles initialization and cleanup of project management infrastructure.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Initialize project discovery and reconcile state.
        """
        from app.domain.project.discovery_manager import discovery_manager
        
        root_projects_dir = SystemConfigService.get_value("WORKSPACE_ROOT")
        if not root_projects_dir:
            logger.warning("[Project] WORKSPACE_ROOT not configured. Skipping discovery.")
            return
            
        if not os.path.exists(root_projects_dir):
            logger.warning(f"[Project] WORKSPACE_ROOT '{root_projects_dir}' does not exist.")
            return

        try:
            # 1. Start Manager
            discovery_manager.start(root_projects_dir)
            
            # 2. Reconcile (Sync filesystem with DB)
            from app.domain.project.sync_service import project_sync_service
            logger.info(f"[Project] Synchronizing projects in {root_projects_dir}...")
            await project_sync_service.reconcile_projects(root_projects_dir)
            logger.info("[Project] ✓ Discovery and synchronization complete")
        except Exception as e:
            logger.error(f"[Project] Startup initialization failed: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING: Stop project discovery manager."""
        try:
            from app.domain.project.discovery_manager import discovery_manager
            discovery_manager.stop()
            logger.info("[Project] Project discovery manager stopped")
        except Exception as e:
            logger.warning(f"[Project] Failed to stop discovery manager: {e}")

    @event_subscribe(SystemEventType.CONTEXT_POLISHING)
    async def on_context_polishing(self, event):
        """Handle system-wide context polishing request."""
        try:
            from app.domain.project.polisher import project_polisher
            await project_polisher.handle_context_polishing(event)
        except Exception as e:
            logger.error(f"[Project] Context polishing failed: {e}")

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")

        if key == "WORKSPACE_ROOT":
            if not new_value or not os.path.exists(new_value):
                logger.warning(f"[Project] New WORKSPACE_ROOT '{new_value}' is invalid or does not exist.")
                return

            try:
                from app.domain.project.sync_service import project_sync_service
                logger.info(f"[Project] WORKSPACE_ROOT changed, reconciling projects in {new_value}...")
                await project_sync_service.reconcile_projects(new_value)
                
                # Restart discovery manager for new path
                from app.domain.project.discovery_manager import discovery_manager
                discovery_manager.stop()
                discovery_manager.start(new_value)
                logger.info(f"[Project] Discovery manager restarted for {new_value}")
                
            except Exception as e:
                logger.error(f"[Project] Failed to handle WORKSPACE_ROOT change: {e}")


@event_register()
class ProjectMemoryContextProvider:
    """
    Provides project context (README, structure, norms) for memory extraction.

    Automatically registered via @event_register and discovered at startup.
    Renders its own markdown fragment via Jinja2 template — memory layer
    only sees the final formatted string.
    """

    @event_subscribe(MEMORY_CONTEXT_GATHER_EVENT_TYPE)
    async def on_context_gather(self, event: MemoryContextGatherEvent) -> None:
        """Render project context fragment and append to event data."""
        project_id = event.data.project_id
        if not project_id:
            return

        project_path = SystemConfigService.get_value("WORKSPACE_ROOT")
        if not project_path:
            logger.debug("[ProjectContextProvider] WORKSPACE_ROOT not set, skipping.")
            return

        try:
            context = await self._build_template_context(project_path)
            if context:
                fragment = render_template(
                    "domain/project/memory_context.j2",
                    **context,
                )
                if fragment.strip():
                    event.data.context_fragments.append(fragment.strip())
        except Exception as e:
            logger.warning(f"[ProjectContextProvider] Failed to render context: {e}")

    async def _build_template_context(self, project_path: str) -> dict | None:
        """Gather raw data and return a dict for the Jinja2 template."""
        from app.domain.project.service import project_context_manager

        readme = ""
        structure = ""

        try:
            loop = asyncio.get_event_loop()
            readme = await loop.run_in_executor(
                None,
                project_context_manager.extract_description_from_readme,
                project_path,
            )
            readme = readme[:1000] if readme else ""
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] README extraction failed: {e}")

        try:
            structure = await project_context_manager.get_project_structure(project_path)
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] Structure extraction failed: {e}")

        norms = []
        try:
            loop = asyncio.get_event_loop()
            norms = await loop.run_in_executor(
                None, self._scan_norm_files_sync, project_path
            )
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] Norms scan failed: {e}")

        if not readme and not structure and not norms:
            return None

        return {
            "readme_summary": readme,
            "project_structure": structure,
            "norms": [{"file": n[0], "content": n[1]} for n in norms] if norms else [],
        }

    def _scan_norm_files_sync(self, project_path: str) -> list[tuple[str, str]]:
        """Synchronous norm file scanner (runs in thread pool).

        Returns list of (filename, content_preview) tuples.
        PROJECT.md receives a larger quota because it is the primary project
        identity document used for domain-term extraction.
        """
        norms = []
        for norm_file in PROJECT_NORM_FILES:
            path = os.path.join(project_path, norm_file)
            if os.path.exists(path) and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        # PROJECT.md is the canonical project profile; give it more space
                        quota = 5000 if norm_file == "PROJECT.md" else 1000
                        content = f.read(quota)
                        norms.append((norm_file, content))
                except Exception:
                    continue
        return norms


@event_register()
class ProjectContextHydrator:
    """
    Subscribes to session start events to resolve project paths and hydrate EvoContext.
    """

    @event_subscribe(SystemEventType.SESSION_STARTED)
    async def on_session_started(self, event) -> None:
        """Resolve project details and enrich EvoContext."""
        logger.info(f"[ProjectHydrator] Received SESSION_STARTED event for project_id: {event.data.get('project_id')}")
        from app.core.context import ContextManager
        from app.core.evocloud import evocloud_manager
        
        ctx = ContextManager.current()
        if not ctx:
            return

        project_id = event.data.get("project_id") or ctx.project_id
        if not project_id or project_id == 0:
            return

        # We always want to fetch and update if we have a valid project_id
        # since ctx.working_directory might just be the default fallback root.

        try:
            project = await evocloud_manager.get_project_by_id(project_id)
            if project and project.get("path"):
                working_dir = project["path"]
                logger.info(f"[ProjectHydrator] Resolved project {project_id} path: {working_dir}")
                
                # Update Context
                ctx.working_directory = working_dir
                
                # Update legacy thread_context_store for backward compatibility
                from app.core.context import thread_context_store
                thread_context_store.set_working_directory(ctx.thread_id, working_dir)
                thread_context_store.set_active_project(ctx.thread_id, project_id)
        except Exception as e:
            logger.warning(f"[ProjectHydrator] Failed to resolve project {project_id}: {e}")
