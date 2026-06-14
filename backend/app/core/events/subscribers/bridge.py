import logging
from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe_all, register_instance_handlers
from app.core.engine.message.event_bus import get_event_bus

logger = logging.getLogger(__name__)


@event_register()
class UniversalBridgeSubscriber:
    """
    The "Master Bridge" for the EvoLoop Event System.
    
    Instead of hardcoded mapping tables, this subscriber inspects every internal 
    event for the 'is_public' metadata flag. If enabled, it automatically 
    translates and broadcasts the event to the external EventBus (UI/WebSocket).
    """

    def __init__(self):
        """
        Initialize the bridge and subscribe to multiple domain buses.
        """
        try:
            from app.core.environment.bus import event_bus as awakening_bus
            # Manually register to the awakening bus (domain-specific)
            # The system_bus registration is handled by the @event_register decorator
            register_instance_handlers(self, awakening_bus)
            logger.info("[UniversalBridge] Multi-bus subscription active (System + Awakening)")
        except ImportError:
            logger.warning("[UniversalBridge] Awakening bus not found, skipping...")

    @event_subscribe_all()
    async def handle_event(self, event: BaseEvent) -> None:
        """
        Listen to all system events and bridge public ones to the external bus.
        """
        # Defensive: some events on the bus are plain Pydantic models, not BaseEvent
        if not isinstance(event, BaseEvent):
            return

        if not getattr(event, "is_public", False):
            return

        event_type = getattr(event, "type_name", type(event).__name__)

        # Extract routing metadata
        channel_type = getattr(event, "broadcast_channel", "system")
        thread_id = getattr(event, "thread_id", None)

        # Determine target channel name
        if channel_type == "chat" and thread_id:
            target_channel = f"chat:{thread_id}:events"
        else:
            # Fallback to system events or global notifications
            target_channel = "system:events"

        try:
            # Standardized payload conversion via BaseEvent's method
            payload = event.to_frontend_payload()

            # Publish to external EventBus (Redis/PubSub)
            # Use app.utils.json for robust serialization of domain objects (messages, etc)
            from app.utils import json as utils_json
            bus = get_event_bus()
            await bus.publish(target_channel, utils_json.dumps(payload, ensure_ascii=False))

            logger.debug(f"[UniversalBridge] Bridged {event_type} -> {target_channel}")
        except Exception as e:
            logger.warning(f"[UniversalBridge] Failed to bridge event {event_type}: {e}")

