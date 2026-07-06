"""
WebChannel — SSE / EventBus transport for Web UI streaming.

Wraps the existing EventBus publish logic. The SSE consumer in
app/api/routes/stream.py subscribes to the same pub/sub channel.
"""

import json
import logging
from typing import Any

from app.core.engine.message.event_bus import get_event_bus
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.infrastructure.pydantic_base import EventBase
from app.models.schemas.events import BaseStreamEvent

from .base import Channel, ChannelContext

logger = logging.getLogger(__name__)


class WebChannel(Channel):
    """SSE transport via the EventBus (local in-memory or Redis pub/sub)."""

    name = "sse"
    accepts_blocks = True
    accepts_stream_events = True

    async def send(
        self,
        payload: MessageBlock | BaseStreamEvent | EventBase,
        ctx: ChannelContext,
    ) -> None:
        """Serialize payload and publish to the chat SSE channel."""
        try:
            channel = f"chat:{ctx.thread_id}:events"

            if isinstance(payload, MessageBlock):
                event = BlockMapper.to_sse(payload, action=ctx.action)
                data_json = event.model_dump_json()
            elif isinstance(payload, BaseStreamEvent):
                data_json = payload.to_json()
            elif hasattr(payload, "model_dump_json"):
                data_json = payload.model_dump_json(exclude_none=True)
            else:
                data_json = str(payload)

            bus = get_event_bus()
            await bus.publish(channel, data_json)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[WebChannel] SSE send failed: %s", e)

    async def send_custom_event(
        self,
        event_type: str,
        data: dict[str, Any],
        ctx: ChannelContext,
    ) -> None:
        """Publish a custom structured event to the chat SSE channel."""
        try:
            payload = {
                "type": event_type,
                "data": data,
                "thread_id": ctx.thread_id,
                "project_id": ctx.project_id,
            }
            bus = get_event_bus()
            await bus.publish(f"chat:{ctx.thread_id}:events", json.dumps(payload))
            logger.debug("[WebChannel] Published custom event %s for thread %s", event_type, ctx.thread_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[WebChannel] Custom event publish failed: %s", e)
