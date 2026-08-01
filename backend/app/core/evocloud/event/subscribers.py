"""
EvoCloud Event Subscribers
==========================

Event subscribers for EvoCloud lifecycle, real-time sync, and WebSocket messages.
"""

import asyncio
import logging
import platform

from app.core.config import settings
from app.core.engine.event.types import AgentEventType
from app.infrastructure.config.service import SystemConfigService
from app.core.engine.rewind import MESSAGES_CLEANUP, MessagesCleanupEvent
from app.core.events import BaseEvent, SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.schemas.canonical import create_envelope

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

    def __init__(self):
        self._warm_cache_task: asyncio.Task | None = None

    async def _warm_evocloud_cache(self):
        """Background task to warm EvoCloud projects cache."""
        try:
            await asyncio.sleep(1)
            projects = await evocloud_manager.scan_projects()
            logger.info(f"[EvoCloud] ✓ Projects cache warmed: {len(projects)} projects")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[EvoCloud] Cache warming failed: {e}")

    async def _start_services(self):
        """Start EvoCloud services (WebSocket link + cache warming)."""
        await evocloud_manager.start()
        self._warm_cache_task = asyncio.create_task(self._warm_evocloud_cache())

    async def _stop_services(self):
        """Stop EvoCloud services and cancel background cache warming."""
        if self._warm_cache_task and not self._warm_cache_task.done():
            self._warm_cache_task.cancel()
            try:
                await self._warm_cache_task
            except asyncio.CancelledError:
                pass
            self._warm_cache_task = None
        await evocloud_manager.stop()

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Initialize EvoCloud services when application starts.
        If a persisted token exists (e.g. service restart), auto-start services.
        """
        logger.debug("[EvoCloud] Application started, initializing...")
        try:
            if evocloud_manager.api and await evocloud_manager.api.get_token():
                logger.debug("[EvoCloud] Found persisted token, starting services...")
                await self._start_services()
            else:
                logger.debug("[EvoCloud] No token found, skipping auto-start. Will start on USER_LOGGED_IN.")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[EvoCloud] Failed to start services: {e}")

    @event_subscribe(SystemEventType.USER_LOGGED_IN)
    async def on_user_logged_in(self, event):
        """Start EvoCloud services when user logs in."""
        logger.debug("[EvoCloud] User logged in, starting services...")
        try:
            await self._start_services()
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[EvoCloud] Failed to start services on login: {e}")

    @event_subscribe(SystemEventType.USER_LOGGED_OUT)
    async def on_user_logged_out(self, event):
        """Stop EvoCloud services when user logs out."""
        logger.debug("[EvoCloud] User logged out, stopping services...")
        try:
            await self._stop_services()
            logger.debug("[EvoCloud] Services stopped successfully")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[EvoCloud] Error during logout shutdown: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Clean up EvoCloud resources when application stops.
        """
        logger.debug("[EvoCloud] Application stopping, cleaning up...")
        try:
            await self._stop_services()
            logger.debug("[EvoCloud] Services stopped successfully")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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

        # 2. 通过 HTTP relay 通知 Gateway/Mobile 任务已完成（规范 agent.status 格式）
        from app.core.channel import channel_registry
        ch = channel_registry.get("mobile")
        if ch:
            from app.core.identity import identity_service
            device_key = await identity_service.store.get_device_key()
            await ch.send_envelope(
                env_type="agent.status",
                body={
                    "thread_id": getattr(event, 'thread_id', ''),
                    "status": getattr(event, 'status', 'done'),
                },
                target_device_key=device_key,
                member_id=0,
            )


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
        key = event.data.get("key", "")
        if key not in ("EVOCLOUD_DEVICE_NAME", "EVOCLOUD_DEVICE_DESCRIPTION"):
            return

        new_value = event.data.get("new_value", "")
        if key == "EVOCLOUD_DEVICE_NAME" and not new_value:
            return

        from app.core.identity import identity_service

        device_key = await identity_service.store.get_device_key()
        if not device_key:
            logger.debug("[EvoCloud] No device_key yet, skipping device info sync")
            return

        from app.core.environment.discovery import EnvironmentProbe
        from app.core.evocloud.bridge.sync_tasks import sync_device_info_task

        info = {
            "device_name": (
                SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME")
                or ""
            ),
            "device_description": (
                SystemConfigService.get_value("EVOCLOUD_DEVICE_DESCRIPTION")
                or ""
            ),
            "device_type": EnvironmentProbe.get_inferred_device_type(),
            "os_info": platform.platform(),
        }
        sync_device_info_task.delay(device_key, info)
        logger.info(
            f"[EvoCloud] Enqueued device info sync for {key} change: "
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

    @event_subscribe(MESSAGES_CLEANUP)
    async def on_messages_cleanup(self, event: MessagesCleanupEvent):
        """
        Listen to local database cleanup during rewind/retry, and propagate
        these deletions to EvoCloud via HTTP API.
        """
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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[EvoCloud] Exception during cloud sync messages cleanup: {e}")
