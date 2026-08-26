"""
Terminal Background Lifecycle Handlers
======================================

Starts the background task cleanup worker on ``APP_STARTED`` and cancels it on
``APP_STOPPING`` so the 24h task eviction loop actually runs.

Registered via ``@event_register`` + ``auto_discover_handlers`` (which scans
``app.core``), so there is no hardcoded dependency in ``app/main.py``: if this
module cannot be imported, discovery logs and skips it.
"""

import asyncio
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class BackgroundTaskLifecycleSubscriber:
    """Lifecycle handlers for the background task manager."""

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        from app.core.execution.terminal.background import task_manager

        await task_manager.start_cleanup_worker()
        logger.info("[Background] 后台任务清理循环已启动")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        from app.core.execution.terminal.background import task_manager

        cleanup_task = getattr(task_manager, "_cleanup_task", None)
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("[Background] 后台任务清理循环已停止")
