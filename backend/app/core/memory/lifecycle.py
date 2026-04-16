"""
Memory Module Lifecycle Handlers
Handles application-level shutdown and session completion events for memory.
"""
import logging
import asyncio
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schema import SessionCompletedEvent

logger = logging.getLogger(__name__)


@event_register()
class MemoryLifecycleHandler:
    """
    Handles application-level lifecycle events for the Memory domain.
    
    Includes:
    - Auto-extraction of conversation history on session completion
    - Graceful shutdown of memory container on app stop
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Trigger automatic memory extraction.
        """
        data = event.data
        logger.info(f"[Memory] 🧠 Session completed for thread {data.thread_id}. Triggering auto-extraction...")

        try:
            from app.core.memory.auto_extraction import trigger_auto_extraction
            # Fire and forget auto-extraction in a background task
            asyncio.create_task(
                trigger_auto_extraction(
                    thread_id=data.thread_id,
                    messages=data.messages,
                    project_id=data.project_id,
                    user_id=data.user_id,
                )
            )
            logger.debug(f"[Memory] ✓ Auto-extraction background task started for {data.thread_id}")
        except Exception as e:
            logger.error(f"[Memory] Failed to trigger auto-extraction: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING event - shutdown memory container."""
        try:
            from app.core.memory.lifespan import MemoryLifespanManager
            await MemoryLifespanManager.shutdown()
            logger.info("[Memory] Memory container shutdown")
        except Exception as e:
            logger.warning(f"[Memory] Failed to shutdown memory container: {e}")
