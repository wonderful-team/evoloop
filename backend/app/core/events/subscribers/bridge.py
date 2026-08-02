import logging

from app.core.channel import ChannelContext, channel_registry
from app.core.events.base import BaseEvent
from app.core.events.decorators import (
    event_register,
    event_subscribe_all,
)

logger = logging.getLogger(__name__)


@event_register()
class UniversalBridgeSubscriber:
    """
    The "Master Bridge" for the EvoLoop Event System.

    Instead of hardcoded mapping tables, this subscriber inspects every internal
    event for the 'is_public' metadata flag. If enabled, it automatically
    forwards the event to the ChannelRegistry for outbound streaming.

    Channel selection is delegated to OutputChannelPolicy — the single authority
    for deciding which channels receive a given payload.
    """

    def __init__(self):
        """Initialize the bridge."""
        pass

    @event_subscribe_all()
    async def handle_event(self, event: BaseEvent) -> None:
        """
        Listen to all system events and bridge public ones to the external channels.
        """
        # Defensive: some events on the bus are plain Pydantic models, not BaseEvent
        if not isinstance(event, BaseEvent):
            return

        if not event.is_public:
            return

        event_type = event.type_name
        thread_id = event.thread_id

        ctx = ChannelContext(
            thread_id=thread_id or "system",
            project_id=getattr(event, "project_id", None)
        )

        try:
            # Forward the public system event to Web UI via ChannelRegistry (sse) and voice
            selected = channel_registry.select({"sse", "voice"}, payload_is_block=False)
            for ch in selected:
                await ch.send(event, ctx)

        except Exception as e:
            logger.warning(f"[UniversalBridge] Failed to bridge event {event_type}: {e}")
