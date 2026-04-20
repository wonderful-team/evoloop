"""
EvoCloud Event Handlers
"""
import asyncio
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.bridge.handlers import (
    handle_remote_command,
    handle_project_switch_event,
)
from app.core.evocloud.bridge.query_handler import handle_query_request

logger = logging.getLogger(__name__)


@event_register()
class EvoCloudLifecycleHandler:
    """
    Handles EvoCloud-related system events.
    
    Includes:
    - Starting EvoCloud services on app start
    - Syncing cloud projects to local
    - Cleaning up resources on app stop
    """

    async def _warm_evocloud_cache(self):
        """Background task to warm EvoCloud projects cache."""
        try:
            await asyncio.sleep(1)
            projects = await evocloud_manager.scan_projects()
            logger.info(f"[EvoCloud] ✓ Projects cache warmed: {len(projects)} projects")
        except Exception as e:
            logger.warning(f"[EvoCloud] Cache warming failed: {e}")

    async def _sync_cloud_project(self):
        """
        Sync current cloud project to local workspace.
        """
        try:
            import os
            from app.core.context import thread_context_store
            from app.domain.codebase.indexing.manager import indexing_manager
            from app.domain.codebase.indexing.service import IndexingService
            from app.domain.project import cache as project_cache

            res = await evocloud_manager.api.get_current_project()
            if res.get("code") == 0:
                project_data = res.get("data", {})
                cloud_path = project_data.get("external_path")
                if cloud_path and os.path.exists(cloud_path):
                    is_ignored = await project_cache.is_path_ignored(cloud_path)
                    if not is_ignored:
                        service = IndexingService()
                        existing_repo = await service.get_repo_by_path(cloud_path)
                        if existing_repo and existing_repo.sync_status == "IGNORED":
                            is_ignored = True
                    
                    if is_ignored:
                        logger.info(f"[EvoCloud] Skipping cloud project sync for ignored path: {cloud_path}")
                    else:
                        logger.info(f"[EvoCloud] Synced active project from Cloud: {cloud_path}")
                        thread_context_store.set_working_directory("default", cloud_path)
                        repo_name = os.path.basename(cloud_path)
                        repo = await IndexingService().get_or_create_repo(cloud_path, repo_name)
                        await indexing_manager.start_watching(cloud_path, repo.id)
            else:
                logger.warning(f"[EvoCloud] Failed to fetch current project: {res.get('message')}")
        except Exception as e:
            logger.warning(f"[EvoCloud] Error syncing cloud project: {e}")

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Initialize EvoCloud services when application starts.
        """
        logger.info("[EvoCloud] Application started, initializing...")
        try:
            if evocloud_manager.api and evocloud_manager.api.get_token():
                logger.info("[EvoCloud] Found persisted token, registering handlers and starting services...")
                
                # Register Bridge Handlers
                evocloud_manager.set_command_handler(handle_remote_command)
                evocloud_manager.set_event_handler(handle_project_switch_event)
                evocloud_manager.set_query_handler(handle_query_request)
                
                await evocloud_manager.start()
                await self._sync_cloud_project()
                asyncio.create_task(self._warm_evocloud_cache())
            else:
                logger.info("[EvoCloud] No token found, skipping auto-start")
        except Exception as e:
            logger.error(f"[EvoCloud] Failed to start services: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Clean up EvoCloud resources when application stops.
        """
        logger.info("[EvoCloud] Application stopping, cleaning up...")
        try:
            await evocloud_manager.stop()
            logger.info("[EvoCloud] Services stopped successfully")
        except Exception as e:
            logger.error(f"[EvoCloud] Error during shutdown: {e}")
