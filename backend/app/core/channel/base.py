"""
Channel — abstract base for all message delivery transports.

A Channel owns:
- Serialization of canonical payloads (MessageBlock / BaseStreamEvent) into transport-specific format
- Transport dispatch (publish to EventBus, send via WebSocket, POST to IM webhook, etc.)
- Error handling and fallback logic specific to the transport

Lifecycle:
- Channels are registered once at startup via ChannelRegistry.register()
- Each publish() call on MessagePublisher iterates matching channels and calls send()
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.engine.message.schemas import MessageBlock
from app.infrastructure.pydantic_base import EventBase
from app.models.schemas.events import BaseStreamEvent

logger = logging.getLogger(__name__)


@dataclass
class ChannelContext:
    """Per-publish context passed to every Channel.send() call."""
    thread_id: str
    project_id: int | None = None
    action: str = "create"
    extra: dict[str, Any] = field(default_factory=dict)


class Channel(ABC):
    """
    Abstract transport channel.

    Subclasses implement send() for the main payload path.
    Optional methods (send_hitl_request, send_custom_event) default to no-op
    for transports that don't support them.
    """

    name: str = "base"
    accepts_blocks: bool = True
    accepts_stream_events: bool = False

    @abstractmethod
    async def send(
        self,
        payload: MessageBlock | BaseStreamEvent | EventBase,
        ctx: ChannelContext,
    ) -> None:
        """Deliver a payload through this transport."""
        ...

    async def send_envelope(
        self,
        env_type: str,
        body: dict[str, Any],
        target_device_key: str | None = None,
        member_id: int = 0,
    ) -> None:
        """Deliver an arbitrary canonical envelope. Override for transports that support it."""
        return

    async def send_custom_event(
        self,
        event_type: str,
        data: dict[str, Any],
        ctx: ChannelContext,
    ) -> None:
        """Deliver a custom structured event. Override for transports that support it."""
        return

    async def send_hitl_request(
        self,
        request_id: str,
        request_type: str,
        prompt: str,
        ctx: ChannelContext,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Deliver a HITL request. Override for transports that support interactive prompts."""
        return

    async def start(self) -> None:
        """Optional startup hook (open connections, warm caches)."""
        return

    async def stop(self) -> None:
        """Optional shutdown hook (close connections, flush buffers)."""
        return
