"""
Memory Module Event Handlers
"""
import logging
import asyncio
from app.core.events import system_bus, SystemEventType
from app.core.events.schema import SessionCompletedEvent

logger = logging.getLogger(__name__)


async def on_session_completed(event: SessionCompletedEvent):
    """
    Handle session completion by triggering automatic knowledge/memory extraction.
    """
    data = event.data
    logger.info(f"[Memory] 🧠 Session completed event received for thread {data.thread_id}. Triggering auto-extraction...")

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


def register_memory_event_handlers():
    """Register memory event handlers with the system bus."""
    system_bus.subscribe(SystemEventType.SESSION_COMPLETED, on_session_completed)
    logger.info("[Memory] Event handlers registered")


# Self-register on import
register_memory_event_handlers()
