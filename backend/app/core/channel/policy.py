"""
OutputChannelPolicy — 唯一的出站通道决策权威。

所有出站 payload（MessageBlock、TokenEvent、BaseEvent）的目标通道
在此处统一决定。Publisher 和 Bridge 只负责按给定 channels 搬运。

决策依据：
  - session_source: EvoContext.metadata.source（"voice" / "web" / "mobile" / ...）
                    由 current_session_source ContextVar 提供（engine.py 在节点启动时 set）
  - node_source:    current_node_source ContextVar（"supervisor" / "worker" / "finish" / None）
  - payload 类型
  - MessageBlock.status（streaming vs completed）

规则真值表（在此处集中维护，不散落各处）：

  | payload 类型       | status      | node_source     | session_source | → channels            |
  |--------------------|-------------|-----------------|----------------|-----------------------|
  | TokenEvent         | —           | supervisor      | voice          | {sse, voice}          |
  | TokenEvent         | —           | worker/finish/* | voice          | {sse}                 |
  | TokenEvent         | —           | *               | web/mobile/*   | {sse}                 |
  | ThinkingEvent      | —           | supervisor      | voice          | {sse, voice}          |
  | ThinkingEvent      | —           | worker/finish/* | voice          | {sse}                 |
  | ProgressEvent      | —           | supervisor      | voice          | {sse, voice}          |
  | ProgressEvent      | —           | worker/finish/* | voice          | {sse}                 |
  | AI MessageBlock    | streaming   | supervisor      | voice          | {sse, voice}          |
  | AI MessageBlock    | streaming   | worker/finish/* | voice          | {sse}                 |
  | AI MessageBlock    | streaming   | *               | web/mobile/*   | {sse}                 |
  | AI MessageBlock    | completed   | supervisor      | voice          | {sse, mobile, voice}  |
  | AI MessageBlock    | completed   | worker/finish/* | voice          | {sse, mobile}         |
  | AI MessageBlock    | completed   | *               | web/mobile/*   | {sse, mobile}         |
  | Tool MessageBlock  | streaming   | *               | *              | {sse}                 |
  | Tool MessageBlock  | completed   | *               | *              | {sse, mobile}         |
  | Human MessageBlock | completed   | mobile          | *              | {sse}                 |
  | Human MessageBlock | completed   | web/*           | *              | {sse, mobile}         |
  | BaseEvent (public) | —           | finish/*        | voice          | {sse, voice}          |
  | BaseEvent (public) | —           | *               | web/mobile/*   | {sse}                 |
  | Other/unknown      | —           | *               | *              | {sse}                 |

注意：
  - Tool / Human MessageBlock 默认也走 policy；如有特殊场景需要显式传入 channels，
    调用处必须注释说明为什么绕过 policy（当前仅剩 transient/error/HITL 消息需要）。
  - VoiceChannel 内部仍保留对非 voice source 的兜底过滤，作为 defense-in-depth。
"""

from __future__ import annotations

import contextvars
import logging

from app.core.engine.message.schemas import MessageBlock
from app.core.events.base import BaseEvent
from app.models.schemas.events import (
    ProgressEvent,
    ThinkingEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)

#: Thread-scoped session source ("voice"/"web"/"mobile") used by OutputChannelPolicy.
#: Set by AgentEngine.run_node() from EvoContext.metadata.source.
current_session_source: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_source", default=None
)


def _is_voice_session(session_source: str | None) -> bool:
    return session_source == "voice"


def _is_supervisor(node_source: str | None) -> bool:
    return node_source == "supervisor"


def _is_streaming_block(block: object) -> bool:
    return getattr(block, "status", "") in ("streaming", "running")


class OutputChannelPolicy:
    """
    Single authority for deciding which output channels receive a given payload.

    Call ``resolve()`` with the payload and routing context.
    Returns a set of channel names (e.g. {"sse", "voice", "mobile"}).
    """

    @classmethod
    def resolve(
        cls,
        payload: object,
        session_source: str | None,
        node_source: str | None,
    ) -> set[str]:
        """
        Decide the target channels for an outbound payload.

        Args:
            payload:        The outbound object (MessageBlock, TokenEvent, BaseEvent, …).
            session_source: The session's origin ("voice", "web", "mobile", …).
                            Typically comes from ``current_session_source`` ContextVar.
            node_source:    The agent node currently executing ("supervisor", "worker", …).
                            Typically comes from ``current_node_source`` ContextVar.

        Returns:
            A set of channel names to deliver the payload to.
        """
        channels = cls._resolve(payload, session_source, node_source)
        return channels

    # ── Internal helpers ────────────────────────────────────────────────────────

    @classmethod
    def _resolve(
        cls,
        payload: object,
        session_source: str | None,
        node_source: str | None,
    ) -> set[str]:
        if isinstance(payload, (TokenEvent, ThinkingEvent, ProgressEvent)):
            return cls._resolve_stream_event(session_source, node_source)

        if isinstance(payload, MessageBlock):
            return cls._resolve_message_block(payload, session_source, node_source)

        if isinstance(payload, BaseEvent):
            return cls._resolve_base_event(payload, session_source, node_source)

        logger.debug(
            "[OutputChannelPolicy] Unknown payload type %s -> default {sse}",
            type(payload).__name__,
        )
        return {"sse"}

    @classmethod
    def _resolve_stream_event(
        cls,
        session_source: str | None,
        node_source: str | None,
    ) -> set[str]:
        """TokenEvent / ThinkingEvent / ProgressEvent routing."""
        if _is_voice_session(session_source) and _is_supervisor(node_source):
            # Only Supervisor tokens go to voice — this is the core bug fix.
            return {"sse", "voice"}
        return {"sse"}

    @classmethod
    def _resolve_message_block(
        cls,
        block: MessageBlock,
        session_source: str | None,
        node_source: str | None,
    ) -> set[str]:
        """MessageBlock routing by role, status and node origin."""
        role = getattr(block, "role", "")
        streaming = _is_streaming_block(block)

        if role == "human":
            # Mobile gateway already syncs the original human message to mobile;
            # avoid echoing it back through our own mobile channel.
            if session_source == "mobile":
                return {"sse"}
            return {"sse", "mobile"}

        if role == "tool":
            if streaming:
                return {"sse"}
            return {"sse", "mobile"}

        if role == "ai":
            if streaming:
                if _is_voice_session(session_source) and _is_supervisor(node_source):
                    return {"sse", "voice"}
                return {"sse"}
            # completed / pending / failed etc.
            if _is_voice_session(session_source) and _is_supervisor(node_source):
                return {"sse", "mobile", "voice"}
            return {"sse", "mobile"}

        # system / unknown roles
        return {"sse", "mobile"}

    @classmethod
    def _resolve_base_event(
        cls,
        event: BaseEvent,
        session_source: str | None,
        node_source: str | None,
    ) -> set[str]:
        """System lifecycle event (SessionCompletedEvent, AgentRunCompletedEvent, …) routing."""
        # If the event itself carries a source, prefer it over the ContextVar.
        event_source = getattr(event, "source", None) or getattr(
            getattr(event, "data", None), "source", None
        )
        effective_source = event_source or session_source

        if _is_voice_session(effective_source):
            return {"sse", "voice"}
        return {"sse"}
