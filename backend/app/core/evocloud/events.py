"""
EvoCloud Event Handlers
"""
import asyncio
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.engine.events import AgentEventType
from app.core.evocloud.manager import evocloud_manager
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

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Initialize EvoCloud services when application starts.

        Responsibilities (transport layer only):
        - Register query handler
        - Start WebSocket link
        - Warm EvoCloud projects cache

        Project sync (setting working directory, repo creation, indexing)
        is handled by ``ProjectDomainHandler.on_application_started`` in
        the domain layer.
        """
        logger.info("[EvoCloud] Application started, initializing...")
        try:
            if evocloud_manager.api and evocloud_manager.api.get_token():
                logger.info("[EvoCloud] Found persisted token, registering handlers and starting services...")
                evocloud_manager.set_query_handler(handle_query_request)
                await evocloud_manager.start()
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


@event_register()
class EvoCloudSyncHandler:
    """
    Handles real-time conversation sync triggers.

    Subscribes to agent run completion events and immediately
    triggers incremental sync to push new messages to Member Center.
    """

    @event_subscribe(AgentEventType.RUN_COMPLETED)
    async def on_agent_run_completed(self, event):
        """
        Triggered when an agent run finishes.
        Immediately schedules an incremental sync so messages
        don't wait for the next 5-minute polling cycle.
        """
        from app.core.evocloud.bridge.conversation_sync import _conversation_sync_manager

        if _conversation_sync_manager is None:
            logger.debug("[EvoCloudSync] No sync manager active, skipping")
            return

        try:
            await _conversation_sync_manager._schedule_incremental_sync()
            logger.info(
                f"[EvoCloudSync] Incremental sync triggered by run completion "
                f"for thread {getattr(event, 'thread_id', 'unknown')}"
            )
        except Exception as e:
            logger.warning(f"[EvoCloudSync] Failed to trigger incremental sync: {e}")
