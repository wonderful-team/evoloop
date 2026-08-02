"""
MessagePublisher — unified outbound dispatcher.

Two payload families, two routing strategies:

1. System Events (BaseEvent): routed through ``system_bus`` — the canonical process-wide event bus in ``app.core.events``. It delivers to in-process Python subscribers, and ``UniversalBridgeSubscriber`` forwards public events to the Redis SSE stream for frontends.

2. Stream Events (BaseStreamEvent) and MessageBlocks (persisted chat messages): dispatched directly through ``ChannelRegistry`` to registered output channels (WebChannel → Redis SSE, MobileChannel → device push, ...).

Usage:
    from app.core.engine.message.publisher import MessagePublisher

    publisher = MessagePublisher(thread_id="xxx")
    await publisher.publish(block)          # MessageBlock → channels (WebChannel & MobileChannel)
    await publisher.publish(stream_event)   # BaseStreamEvent → WebChannel (SSE)
"""

import logging

from app.core.channel import ChannelContext, channel_registry
from app.core.engine.message.schemas import MessageBlock
from app.models.schemas.events import BaseStreamEvent

logger = logging.getLogger(__name__)


class MessagePublisher:
    """Unified outbound dispatcher: message blocks and streaming events -> channels."""

    def __init__(self, thread_id: str, project_id: int | None = None):
        self.thread_id = thread_id
        self.project_id = project_id

    async def publish(
        self,
        payload: MessageBlock | BaseStreamEvent,
        channels: set[str] | None = None,
        action: str = "create",
    ) -> None:
        """
        Unified dispatch entry for outbound transport.

        Payloads (MessageBlock, BaseStreamEvent) are dispatched through
        ChannelRegistry to registered output channels (WebChannel SSE, Mobile Push, etc).

        Channel routing:
        - If ``channels`` is explicitly provided (non-None), it is used as-is.
          This is an escape hatch for transient/error/HITL messages that must
          never reach mobile or voice (each caller must document why it bypasses
          policy).
        - Otherwise, ``OutputChannelPolicy.resolve()`` decides the channels based
          on session_source and node_source ContextVars — the single authoritative decision point.
        """
        if channels is None:
            from app.core.channel.policy import OutputChannelPolicy, current_session_source
            from app.core.context.manager import ContextManager
            from app.core.engine.callbacks.database_logger import current_node_source

            node_src = current_node_source.get()
            session_src = current_session_source.get()
            # Fallback to EvoContext.metadata.source for callers running outside
            # an active AgentEngine node (e.g. dispatch_agent_run publishing the
            # persisted human message before the background agent starts).
            if session_src is None:
                ctx = ContextManager.current()
                session_src = getattr(ctx.metadata, "source", None)
            channels = OutputChannelPolicy.resolve(payload, session_src, node_src)
        else:
            channels = set(channels)

        ctx = ChannelContext(
            thread_id=self.thread_id,
            project_id=self.project_id,
            action=action,
        )

        payload_is_block = isinstance(payload, MessageBlock)
        selected = channel_registry.select(channels, payload_is_block=payload_is_block)

        for ch in selected:
            try:
                await ch.send(payload, ctx)
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning("[Publisher] Channel '%s' send failed: %s", ch.name, e)

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
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning("[Publisher] Channel '%s' HITL send failed: %s", ch.name, e)
