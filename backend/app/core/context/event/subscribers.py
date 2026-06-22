"""
Context Module Lifecycle Handlers
Handles application-level events for the context system.
"""
import logging
import os

from app.core.engine.event.schemas import ConversationDeletedEvent
from app.core.engine.event.types import ConversationEventType
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class ContextLifecycleSubscriber:
    """
    Handles initialization and updates of the context management system.
    """

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")

        if key == "WORKSPACE_ROOT":
            try:
                from app.core.context import thread_context_store
                if new_value:
                    abs_path = os.path.abspath(new_value)
                    thread_context_store._default_root = abs_path
                    logger.info(f"[Context] Updated ThreadContextStore default root to: {abs_path}")
            except Exception as e:
                logger.error(f"[Context] Failed to update ThreadContextStore on config change: {e}")

    @event_subscribe(ConversationEventType.CONVERSATION_DELETED)
    async def on_conversation_deleted(self, event: ConversationDeletedEvent) -> None:
        thread_id = event.thread_id
        from app.core.context import thread_context_store, tool_state_store
        thread_context_store.clear_context(thread_id)
        tool_state_store.clear_thread(thread_id)
        logger.info(f"[Context] Cleared in-memory context for thread {thread_id}")
