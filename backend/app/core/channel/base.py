"""
Channel — abstract base for all message delivery transports (output)
and message intake transports (input).

Output subclasses implement send() for the main payload path.
Input subclasses implement receive() for listening and normalizing
incoming messages from source-specific transports.
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


# ── Output Channel (publish agent results) ─────────────────────────


class Channel(ABC):
    """
    Abstract transport channel for delivering agent results
    to external clients (SSE, WebSocket, mobile push, etc.).
    """

    name: str = "base"
    accepts_blocks: bool = True
    accepts_stream_events: bool = False

    # 该渠道所属场景（source 场景标识，如 voice/web/mobile/duty）。
    # 空集合 = 不声明场景（按 name 精确匹配）。声明后 OutputChannelPolicy
    # 可用场景名（如 "duty"）路由到本渠道，实现「场景标识」与「渠道实现」解耦。
    scenes: set[str] = set()

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
        """Deliver an arbitrary canonical envelope."""
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
        """Deliver a HITL request (default no-op, override per channel).

        Implementation matrix:
        - ``WebChannel`` (``sse``): intentionally NOT implemented — the web UI
          receives HITL requests via the SSE activity snapshot
          (``/stream`` → ``human_request`` event) + MessageBroker events, not
          through this channel push.
        - ``VoiceChannel``: intentionally NOT implemented — voice has no
          interactive HITL UI; HITL in voice mode surfaces as a status change.
        - ``MobileChannel``: implemented — pushes ``hitl.request`` via the
          Gateway HTTP API.
        """
        return

    async def start(self) -> None:
        """Optional startup hook."""
        return

    async def stop(self) -> None:
        """Optional shutdown hook."""
        return


# ── Input Channel (ingest user messages) ───────────────────────────


@dataclass
class IncomingMessage:
    """Normalized user message ready for agent dispatch.

    Every source (voice, mobile, web) produces this same structure.
    """

    source: str
    thread_id: str
    text: str
    project_id: int = 0
    references: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    member_id: int = 0
    command_id: int | None = None
    message_id: str | None = None
    checkpoint_id: str | None = None
    model: str | None = None
    context: Any = None
    is_retry: bool = False
    skip_message_persistence: bool = False


class InputChannel(ABC):
    """
    Abstract transport channel for receiving and normalizing
    user messages from a specific source (voice WS, mobile relay,
    web chat HTTP, etc.).

    Each implementation:
    1. Listens on its transport (or is triggered by an upstream handler)
    2. Builds an IncomingMessage from the raw data
    3. Calls dispatch() to submit to the agent engine
    """

    name: str = "base"

    @abstractmethod
    async def receive(self, raw: Any, **kwargs: Any) -> IncomingMessage | None:
        """Parse source-specific raw data into a normalized IncomingMessage.

        Returns None if the message should be skipped (e.g. non-chat control signal).
        """
        ...

    async def dispatch(self, msg: IncomingMessage) -> Any:
        """Submit a normalized message to the agent engine."""
        from app.core.engine.dispatch import dispatch_agent_run

        # 客服等文本通道统一补齐 intent_hint（skip_l0=True：duty 场景不执行
        # L0 模板宏），与 web/mobile 入口取得同等质量的先验上下文。
        # 函数内 import：routing.dispatch_handler 依赖本模块的类型，避免循环。
        if not (msg.metadata or {}).get("intent_hint"):
            from app.core.routing.dispatch_handler import command_router

            decision = await command_router.resolve(
                msg.text or "",
                thread_id=msg.thread_id,
                project_id=msg.project_id or 0,
                source=msg.source or "duty",
                skip_l0=True,
            )
            if decision.intent_hint:
                msg.metadata = msg.metadata or {}
                msg.metadata["intent_hint"] = (
                    decision.intent_hint.model_dump()
                    if hasattr(decision.intent_hint, "model_dump")
                    else decision.intent_hint
                )

        return await dispatch_agent_run(
            thread_id=msg.thread_id,
            message_content=msg.text,
            project_id=msg.project_id,
            references=msg.references,
            command_id=msg.command_id,
            model=msg.model,
            context=msg.context,
            metadata=msg.metadata,
            member_id=msg.member_id,
            source=msg.source,
            message_id=msg.message_id,
            checkpoint_id=msg.checkpoint_id,
            is_retry=msg.is_retry,
            skip_message_persistence=msg.skip_message_persistence,
        )
