"""
Monitoring Module Event Handlers
"""
import logging
from app.core.events import system_bus, SystemEventType
from app.core.events.schema import SessionCompletedEvent
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


async def on_session_completed(event: SessionCompletedEvent):
    """
    Handle session completion by ending the observability run.
    """
    data = event.data
    logger.info(f"[Monitoring] 📊 Session completed event received for thread {data.thread_id}. Finalizing run...")

    try:
        # End observability run
        await activity_monitor.end_run(
            thread_id=data.thread_id,
            status="done",
            final_outcome=data.outcome
        )
        logger.debug(f"[Monitoring] ✓ Observability run finalized for {data.thread_id}")
    except Exception as e:
        logger.error(f"[Monitoring] Failed to finalize observability run: {e}")


def register_monitoring_event_handlers():
    """Register monitoring event handlers with the system bus."""
    system_bus.subscribe(SystemEventType.SESSION_COMPLETED, on_session_completed)
    logger.info("[Monitoring] Event handlers registered")


# Self-register on import
register_monitoring_event_handlers()
