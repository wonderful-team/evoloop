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

            await activity_monitor.end_run(
                thread_id=data.thread_id,
                status=ActivityStatus.DONE,
                final_outcome=data.outcome,
                run_id=data.run_id,
            )
            logger.debug(f"[Monitoring] ✓ Observability run finalized for {data.thread_id}")
        except Exception as e:
            logger.exception(f"[Monitoring] Failed to finalize observability run: {e}")
