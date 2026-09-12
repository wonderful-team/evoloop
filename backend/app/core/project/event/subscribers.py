"""
Project Event Subscribers
=========================

Event subscribers for project lifecycle, synchronization, and memory context.
"""

import logging
import os

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import thread_context_store
from app.core.engine.event.schemas import WebSocketMessageReceivedEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.project.sync_service import ProjectSyncService
from app.core.project.utils import get_project_path, get_workspace_root

from .schemas import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectMovedEvent,
    ProjectSwitchedEvent,
)
from .types import ProjectEventType

logger = logging.getLogger(__name__)


@event_register()
class ProjectSwitchWebSocketSubscriber:
    """
    Handles ``project_switch`` messages from the WebSocket transport layer.

    This class bridges the WebSocket generic event (``WebSocketMessageReceivedEvent``)
    to the domain-specific ``ProjectSwitchedEvent``.
    """

    @event_subscribe(SystemEventType.WEBSOCKET_MESSAGE_RECEIVED)
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        # 1. 使用标准化模型解析 (兼容 payload/content 各种嵌套)
        try:
            from app.core.evocloud.schemas import RemoteCommand

            cmd = RemoteCommand.model_validate(event.payload)
            action = cmd.get_action()
            payload = cmd.get_payload()
        except Exception as e:
            logger.exception(f"[ProjectSwitchWS] Failed to parse message: {e}")
            return

        if action != "project_switch":
            return

        # 2. 提取信息
        raw_pid = payload.get("project_id")
        project_id = raw_pid if raw_pid is not None else cmd.project_id
        project_name = payload.get("project_name") or ""
        path = payload.get("path")

        # 3. 路径解析：严格以本地为真相源
        if project_id and (not path or not project_name):
            from app.core.project.utils import get_project_path

            try:
                resolved_path = await get_project_path(project_id)
                if resolved_path and os.path.isdir(resolved_path):
                    path = resolved_path
                    project_name = project_name or os.path.basename(path)
                    logger.info(
                        f"[ProjectSwitchWS] Auto-resolved project {project_id} -> {path}"
                    )
                else:
                    logger.warning(
                        f"[ProjectSwitchWS] Project {project_id} not found locally. "
                        "Ignoring switch to avoid using a foreign/external path."
                    )
                    return
            except Exception as e:
                logger.exception(
                    f"[ProjectSwitchWS] Failed to resolve project {project_id}: {e}"
                )
                return

        # Prefer authoritative local path even when payload provided a path
        if project_id:
            from app.core.project.utils import get_project_path

            try:
                resolved_path = await get_project_path(project_id)
                if resolved_path and os.path.isdir(resolved_path):
                    path = resolved_path
            except Exception as e:
                logger.debug(
                    f"[ProjectSwitchWS] Local path resolution failed, keeping event path: {e}",
                    exc_info=True,
                )

        if not path or not os.path.isdir(path):
            logger.warning(
                f"[ProjectSwitchWS] Project switch ignored: project_id={project_id} "
                f"has no valid local path (path={path!r})"
            )
            return

        # 4. 发布领域事件
        from app.core.project.event.publishers import publish_project_switched

        await publish_project_switched(
            project_id=project_id if project_id is not None else DEFAULT_PROJECT_ID,
            project_name=project_name,
            path=path,
        )
        logger.info(
            f"[ProjectSwitchWS] SUCCESSFULLY triggered project switch: id={project_id}, path={path}"
        )


@event_register()
class ProjectDomainSubscriber:
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
            logger.exception(f"[ProjectHandlers] Failed to handle project created: {e}")

    @event_subscribe(ProjectEventType.PROJECT_DELETED)
    async def on_project_deleted(self, event: ProjectDeletedEvent) -> None:
        """Handle project deletion."""
        try:
            await self._sync_service.handle_project_deleted(event.path)
        except Exception as e:
            logger.exception(f"[ProjectHandlers] Failed to handle project deleted: {e}")

    @event_subscribe(ProjectEventType.PROJECT_MOVED)
    async def on_project_moved(self, event: ProjectMovedEvent) -> None:
        """Handle project moved."""
        try:
            await self._sync_service.handle_project_moved(
                event.src_path, event.dest_path
            )
        except Exception as e:
            logger.exception(f"[ProjectHandlers] Failed to handle project moved: {e}")

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event) -> None:
        """Sync current cloud project to local workspace on app start (if token exists)."""
        try:
            from app.core.identity import identity_service

            if await identity_service.get_access_token():
                # Defer to the Huey worker: the local workspace scan and the
                # sequential cloud HTTP calls block APP_STARTED for ~1.4s when
                # awaited inline. Watchers stay in the API process
                # (ProjectLifecycleSubscriber.reconcile_projects).
                from app.core.project.sync_tasks import sync_cloud_projects_task

                sync_cloud_projects_task.delay()
                logger.info("[ProjectHandlers] Cloud project sync dispatched to worker")
            else:
                logger.info(
                    "[ProjectHandlers] No token on startup, skipping project sync. Will sync on USER_LOGGED_IN."
                )
        except Exception as e:
            logger.exception(
                f"[ProjectHandlers] Failed to sync cloud project on start: {e}"
            )

    @event_subscribe(SystemEventType.USER_LOGGED_IN)
    async def on_user_logged_in(self, event) -> None:
        """Sync current cloud project when user logs in."""
        logger.info("[ProjectHandlers] User logged in, syncing cloud project...")
        try:
            await self._sync_service.sync_cloud_project()
        except Exception as e:
            logger.exception(
                f"[ProjectHandlers] Failed to sync cloud project on login: {e}"
            )

    @event_subscribe(ProjectEventType.PROJECT_SWITCHED)
    async def on_project_switched(self, event: ProjectSwitchedEvent) -> None:
        """
        Handle project switch from WebSocket.

        Updates thread_context_store working directory and active project.
        Also updates SharedState so voice routes pick up the new project_id.
        Other modules (indexing, UI) subscribe to the same ProjectSwitchedEvent
        directly — no need to re-publish a duplicate event.
        """
        project_id = event.project_id
        project_name = event.project_name
        path = event.path

        # Update SharedState so voice.route picks up the new project_id
        from app.core.state import shared_state

        await shared_state.set("project_id", str(project_id))

        # Rebuild L0 RouteCatalog so preset + current project macros are available
        from app.core.routing.matcher_cache import matcher_cache

        await matcher_cache.invalidate_and_schedule_rebuild()

        if path:
            if not os.path.isdir(path):
                logger.warning(
                    f"[ProjectHandlers] Project switch received but path does not exist: {path}. Ignoring."
                )
                return
            logger.info(
                f"[ProjectHandlers] Switching project: {project_id} ({project_name}) -> {path}"
            )

            thread_context_store.set_working_directory("remote-default", path)
            thread_context_store.set_working_directory("default", path)

            if project_id:
                thread_context_store.set_active_project("remote-default", project_id)
                thread_context_store.set_active_project("default", project_id)
        elif project_id:
            logger.warning(
                f"[ProjectHandlers] Project switch received but no path provided: {event.model_dump()}"
            )
        else:
            # global(0) 无 path 是正常路径（SSOT 已在上方无条件更新）
            logger.info("[ProjectHandlers] Switched to global workspace (project_id=0)")


@event_register()
class ProjectLifecycleSubscriber:
    """
    Handles initialization and cleanup of project management infrastructure.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Reconcile project state with filesystem.
        """
        root_projects_dir = get_workspace_root()
        if not root_projects_dir:
            logger.warning(
                "[Project] WORKSPACE_ROOT not configured. Skipping reconciliation."
            )
            return

        if not os.path.exists(root_projects_dir):
            logger.warning(
                f"[Project] WORKSPACE_ROOT '{root_projects_dir}' does not exist."
            )
            return

        try:
            from app.core.project.sync_service import project_sync_service

            logger.info(f"[Project] Reconciling projects in {root_projects_dir}...")
            await project_sync_service.reconcile_projects(root_projects_dir)
            logger.info("[Project] ✓ Project reconciliation complete")
        except Exception as e:
            logger.exception(f"[Project] Startup reconciliation failed: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING: cleanup."""
        logger.info("[Project] Application stopping.")

    @event_subscribe(SystemEventType.CONTEXT_POLISHING)
    async def on_context_polishing(self, event):
        """Handle system-wide context polishing request."""
        try:
            from app.core.project.polisher import project_polisher

            await project_polisher.handle_context_polishing(event)
        except Exception as e:
            logger.exception(f"[Project] Context polishing failed: {e}")

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")

        if key == "WORKSPACE_ROOT":
            if not new_value or not os.path.exists(new_value):
                logger.warning(
                    f"[Project] New WORKSPACE_ROOT '{new_value}' is invalid or does not exist."
                )
                return

            try:
                from app.core.project.sync_service import project_sync_service

                await project_sync_service.reconcile_projects(new_value)
                logger.info(f"[Project] ✓ Reconciliation complete for {new_value}")

            except Exception as e:
                logger.exception(
                    f"[Project] Failed to handle WORKSPACE_ROOT change: {e}"
                )


@event_register()
class ProjectContextHydratorSubscriber:
    """
    Subscribes to session start events to resolve project paths and hydrate EvoContext.
    """

    @event_subscribe(SystemEventType.SESSION_STARTED)
    async def on_session_started(self, event) -> None:
        """Resolve project details and enrich EvoContext."""
        logger.info(
            f"[ProjectHydrator] Received SESSION_STARTED event for project_id: {event.data.get('project_id')}"
        )
        from app.core.context import ContextManager, thread_context_store

        ctx = ContextManager.current()
        if not ctx:
            return

        raw_pid = event.data.get("project_id")
        project_id = raw_pid if raw_pid is not None else ctx.project_id
        if project_id is None or project_id == DEFAULT_PROJECT_ID:
            return

        # Only overwrite the working directory when it is missing or still points
        # to the workspace root. If dispatch already resolved a project path, keep it.
        workspace_root = get_workspace_root()
        current_cwd = ctx.working_directory
        if current_cwd and current_cwd != workspace_root and os.path.isdir(current_cwd):
            logger.debug(
                f"[ProjectHydrator] Keeping existing working_directory: {current_cwd}"
            )
            thread_context_store.set_working_directory(ctx.thread_id, current_cwd)
            thread_context_store.set_active_project(ctx.thread_id, project_id)
            return

        try:
            working_dir = await get_project_path(project_id)
            if not working_dir:
                # 多租户（云）项目无本地路径是常态，info 级避免每 run 刷警告
                from app.core.config import settings

                log_fn = logger.info if settings.MULTI_TENANT_MODE else logger.warning
                log_fn(
                    f"[ProjectHydrator] Could not resolve path for project {project_id}"
                )
                return

            # Update Context
            ctx.working_directory = working_dir

            # Update legacy thread_context_store for backward compatibility
            thread_context_store.set_working_directory(ctx.thread_id, working_dir)
            thread_context_store.set_active_project(ctx.thread_id, project_id)
        except Exception as e:
            logger.warning(
                f"[ProjectHydrator] Failed to resolve project {project_id}: {e}",
                exc_info=True,
            )
