"""
EvoCloud Event Subscribers
==========================

Event subscribers for EvoCloud lifecycle, real-time sync, and WebSocket messages.
"""

import asyncio
import logging

from app.core.engine.event.schemas import WebSocketMessageReceivedEvent
from app.core.engine.event.types import AgentEventType
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import QueryResponse
from app.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)


# =============================================================================
# Lifecycle Handler
# =============================================================================

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
            if evocloud_manager.api and await evocloud_manager.api.get_token():
                logger.info("[EvoCloud] Found persisted token, registering handlers and starting services...")
                from app.core.evocloud.bridge.query_handler import handle_query_request
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


# =============================================================================
# Sync Handler
# =============================================================================

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
        sync_manager = evocloud_manager.sync_manager
        if sync_manager is None:
            logger.debug("[EvoCloudSync] No sync manager active, skipping")
            return

        # 1. 触发增量数据库同步（同步到 MC）
        await sync_manager._schedule_incremental_sync()
        logger.info(
            f"[EvoCloudSync] Incremental sync triggered by run completion "
            f"for thread {getattr(event, 'thread_id', 'unknown')}"
        )

        # 2. 通过 WebSocket 实时通知 Gateway/Mobile 任务已完成
        link = evocloud_manager.link
        if link and link.is_connected():
            await link.send_message({
                "type": "agent_run_completed",
                "thread_id": getattr(event, 'thread_id', ''),
                "status": getattr(event, 'status', 'done'),
            })
            logger.debug(f"[EvoCloudSync] Completion signal sent via WebSocket for thread {getattr(event, 'thread_id', '')}")


# =============================================================================
# WebSocket Message Handlers
# =============================================================================

@event_register()
class QueryWebSocketHandler:
    """
    Handles ``query`` messages from Gateway.

    Delegates to the query handler registered on the EvoCloudWebSocketLink.
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "query":
            return
        await self._handle_query(event.raw)

    async def _handle_query(self, data: dict) -> None:
        link = evocloud_manager.link
        if link is None:
            logger.warning("[EvoCloud] Query received but link not available")
            return

        request_id = data.get("request_id")
        query_data = data.get("data", {})
        query_type = query_data.get("query_type")
        thread_id = query_data.get("thread_id")
        params = query_data.get("params", {})

        logger.debug(f"[EvoCloud] Query request: {query_type} (req_id={request_id})")

        result = None
        error = None

        try:
            if link._query_handler:
                if asyncio.iscoroutinefunction(link._query_handler):
                    result = await link._query_handler(query_type, thread_id, params)
                else:
                    result = await run_in_thread(link._query_handler, query_type, thread_id, params)
            else:
                error = "Query handler not registered"
        except Exception as e:
            logger.error(f"[EvoCloud] Query error: {e}")
            error = str(e)

        response = QueryResponse(
            request_id=request_id,
            data={
                "code": 0 if error is None else 500,
                "message": error or "success",
                "request_id": request_id,
                "data": result,
            },
        )
        await link.send_message(response.model_dump())


@event_register()
class InitWebSocketHandler:
    """
    Handles ``init`` messages from Gateway.

    Updates ``client_id`` on the EvoCloudWebSocketLink instance.
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "init":
            return

        client_id = event.payload.get("client_id")
        if not client_id:
            return

        link = evocloud_manager.link
        if link:
            link.client_id = client_id
            logger.info(f"[EvoCloud] client_id updated via event: {client_id}")
