"""
Monitoring Event Subscribers
============================

Event subscribers for monitoring lifecycle.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schemas import SessionCompletedEvent
from app.core.monitoring.constants import ActivityStatus

logger = logging.getLogger(__name__)


@event_register()
class MonitoringLifecycleSubscriber:
    """
    Handles monitoring-related system events.

    This handler ensures that observability runs are properly finalized
    when an agent session completes successfully.
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Finalize the observability run in ActivityMonitor.
        """
        data = event.data
        logger.info(f"[Monitoring] 📊 Session completed for thread {data.thread_id} (Run: {data.run_id}). Finalizing run...")

        try:
            from app.core.monitoring.activity import activity_monitor

            # SessionCompleted 事件本身会经桥接层转成 SSE 的 session_completed；
            # run_end / status 应由 run_scope.__aexit__ 统一发布。此处只把 activity
            # 状态收敛到终态，避免重复发送 terminal SSE。
            await activity_monitor.end_run(
                thread_id=data.thread_id,
                status=ActivityStatus.DONE,
                final_outcome=data.outcome,
                run_id=data.run_id,
                publish_events=False,
            )
            logger.debug(f"[Monitoring] ✓ Observability run finalized for {data.thread_id}")
        except Exception as e:
            logger.exception(f"[Monitoring] Failed to finalize observability run: {e}")
