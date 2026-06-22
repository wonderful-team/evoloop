"""
EvoCloud Event Subscribers
==========================

Event subscribers for EvoCloud lifecycle, real-time sync, and WebSocket messages.
"""

import asyncio
import logging
import platform

from app.core.config import settings
from app.core.engine.event.schemas import WebSocketMessageReceivedEvent
from app.core.engine.event.types import AgentEventType
from app.core.events import BaseEvent, SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import QueryResponse
from app.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)


# =============================================================================
# Lifecycle Handler
# =============================================================================

@event_register()
class EvoCloudLifecycleSubscriber:
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

    async def _start_services(self):
        """Start EvoCloud services (WebSocket link + query handler + cache warming)."""
        from app.core.evocloud.bridge.query_handler import handle_query_request
        evocloud_manager.set_query_handler(handle_query_request)
        await evocloud_manager.start()
        asyncio.create_task(self._warm_evocloud_cache())

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Initialize EvoCloud services when application starts.
        If a persisted token exists (e.g. service restart), auto-start services.
        """
        logger.info("[EvoCloud] Application started, initializing...")
        try:
            if evocloud_manager.api and await evocloud_manager.api.get_token():
                logger.info("[EvoCloud] Found persisted token, starting services...")
                await self._start_services()
            else:
                logger.info("[EvoCloud] No token found, skipping auto-start. Will start on USER_LOGGED_IN.")
        except Exception as e:
            logger.error(f"[EvoCloud] Failed to start services: {e}")

    @event_subscribe(SystemEventType.USER_LOGGED_IN)
    async def on_user_logged_in(self, event):
        """Start EvoCloud services when user logs in."""
        logger.info("[EvoCloud] User logged in, starting services...")
        try:
            await self._start_services()
        except Exception as e:
            logger.error(f"[EvoCloud] Failed to start services on login: {e}")

    @event_subscribe(SystemEventType.USER_LOGGED_OUT)
    async def on_user_logged_out(self, event):
        """Stop EvoCloud services when user logs out."""
        logger.info("[EvoCloud] User logged out, stopping services...")
        try:
            await evocloud_manager.stop()
            logger.info("[EvoCloud] Services stopped successfully")
        except Exception as e:
            logger.error(f"[EvoCloud] Error during logout shutdown: {e}")

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
class EvoCloudSyncSubscriber:
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
        don't wait for the next 30-minute polling cycle.
        """
        if not settings.MOBILE_SYNC_ENABLED:
            return

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
class QueryWebSocketSubscriber:
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
class InitWebSocketSubscriber:
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


# =============================================================================
# Device Info Sync Handler
# =============================================================================

@event_register()
class DeviceInfoSyncSubscriber:
    """
    Triggers asynchronous cloud sync when desktop device metadata changes.

    Currently watches EVOCLOUD_DEVICE_NAME config changes; the same channel can
    be extended for other regular device info fields (os_info, device_type, etc.).
    """

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event: BaseEvent) -> None:
        if event.data.get("key") != "EVOCLOUD_DEVICE_NAME":
            return

        new_value = event.data.get("new_value", "")
        if not new_value:
            return

        from app.core.identity import identity_service

        device_key = await identity_service.store.get_device_key()
        if not device_key:
            logger.debug("[EvoCloud] No device_key yet, skipping device info sync")
            return

        from app.core.evocloud.bridge.sync_tasks import sync_device_info_task
        from app.core.environment.discovery import EnvironmentProbe

        info = {
            "device_name": new_value,
            "device_type": EnvironmentProbe.get_inferred_device_type(),
            "os_info": platform.platform(),
        }
        sync_device_info_task.delay(device_key, info)
        logger.info(
            f"[EvoCloud] Enqueued device info sync for device_name change: "
            f"device_key={device_key[:20]}..."
        )


# =============================================================================
# Rewind & Sync Cleanup Handler
# =============================================================================

@event_register()
class EvoCloudSyncCleanupSubscriber:
    """
    Subscribes to rewind cleanup events and triggers message deletion on cloud sync.
    """

    @event_subscribe("rewind.messages.cleanup")
    async def on_messages_cleanup(self, event: "MessagesCleanupEvent"):
        """
        Listen to local database cleanup during rewind/retry, and propagate
        these deletions to EvoCloud via HTTP API.
        """
        from app.core.engine.rewind.event.schemas import MessagesCleanupEvent
        if not isinstance(event, MessagesCleanupEvent):
            return

        if not event.target_sequence and not event.message_ids:
            return

        from app.core.evocloud.manager import evocloud_manager
        from app.core.identity import identity_service
        
        device_key = await identity_service.store.get_device_key()
        if not device_key:
            return
            
        try:
            if event.target_sequence > 0:
                result = await evocloud_manager.api.sync_rewind_messages(
                    device_key=device_key,
                    thread_id=str(event.thread_id),
                    target_sequence=event.target_sequence,
                    include_target=event.include_target
                )
                if result.get("code") == 0:
                    logger.info(f"[EvoCloud] Successfully rewound cloud messages from sequence {event.target_sequence}")
                else:
                    logger.warning(f"[EvoCloud] Failed to rewind messages from cloud: {result.get('message')}")
            else:
                # Fallback to the old batch deletion API if sequence is 0
                result = await evocloud_manager.api.sync_delete_messages(
                    device_key=device_key,
                    thread_id=str(event.thread_id),
                    message_ids=event.message_ids
                )
                if result.get("code") == 0:
                    logger.info(f"[EvoCloud] Successfully deleted {len(event.message_ids)} messages from cloud via fallback")
                else:
                    logger.warning(f"[EvoCloud] Failed to delete messages from cloud via fallback: {result.get('message')}")
        except Exception as e:
            logger.error(f"[EvoCloud] Exception during cloud sync messages cleanup: {e}")
