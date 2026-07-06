"""
MessagePublisher — unified message dispatcher.

Delegates to registered Channel implementations via ChannelRegistry.
New transports (WeChat, Feishu, DingTalk, Telegram, Slack, ...) are
added by implementing Channel and registering with channel_registry —
no changes to MessagePublisher needed.

Usage:
    from app.core.engine.message.schemas import MessageBlock
    from app.core.engine.message.publisher import MessagePublisher

    block = BlockMapper.from_db(db_msg)
    publisher = MessagePublisher(thread_id="xxx")
    await publisher.publish(block)
"""

import logging
from datetime import datetime
from typing import Any

from app.core.channel import ChannelContext, channel_registry
from app.core.engine.message.schemas import MessageBlock
from app.infrastructure.pydantic_base import EventBase
from app.models.schemas.events import BaseStreamEvent
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class MessagePublisher:
    """Unified message dispatcher: MessageBlock / BaseStreamEvent -> registered channels."""

    def __init__(self, thread_id: str, project_id: int | None = None):
        self.thread_id = thread_id
        self.project_id = project_id

    async def publish(
        self,
        payload: MessageBlock | BaseStreamEvent | EventBase,
        channels: set[str] | None = None,
        action: str = "create",
    ) -> None:
        """
        Unified dispatch entry: deliver payload to registered channels.

        Args:
            payload: MessageBlock (persisted message) or BaseStreamEvent (transient stream event)
            channels: Requested channel names. None = auto-select by payload type.
            action: SSE action for MessageBlock (create/update/append)
        """
        if channels is None:
            channels = {"sse", "mobile"} if isinstance(payload, MessageBlock) else {"sse"}

        ctx = ChannelContext(
            thread_id=self.thread_id,
            project_id=self.project_id,
            action=action,
        )

        is_block = isinstance(payload, MessageBlock)
        selected = channel_registry.select(channels, payload_is_block=is_block)

        for ch in selected:
            try:
                await ch.send(payload, ctx)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning("[Publisher] Channel '%s' send failed: %s", ch.name, e)

    async def publish_custom_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish a custom structured event to all channels that support it."""
        ctx = ChannelContext(thread_id=self.thread_id, project_id=self.project_id)
        for ch in channel_registry:
            try:
                await ch.send_custom_event(event_type, data, ctx)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning("[Publisher] Channel '%s' custom event failed: %s", ch.name, e)

    async def publish_error(
        self,
        title: str,
        message: str,
        error_type: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Push a system error message block."""
        block = MessageBlock(
            id=gen_uuid(),
            thread_id=self.thread_id,
            role="system",
            category="error_system",
            content=message,
            content_type="text",
            status="failed",
            is_visible=True,
            created_at=datetime.now().isoformat(),
            meta_data={
                "title": title,
                "error_type": error_type,
                **(metadata or {}),
            },
        )
        await self.publish(block)

    async def publish_hitl_request(
        self,
        request_id: str,
        request_type: str,
        prompt: str,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Push a HITL request to all channels that support interactive prompts."""
        ctx = ChannelContext(thread_id=self.thread_id, project_id=self.project_id)
        for ch in channel_registry:
            try:
                await ch.send_hitl_request(
                    request_id=request_id,
                    request_type=request_type,
                    prompt=prompt,
                    ctx=ctx,
                    options=options,
                    context=context,
                    default_value=default_value,
                    tool_name=tool_name,
                    metadata=metadata,
                )
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning("[Publisher] Channel '%s' HITL send failed: %s", ch.name, e)
