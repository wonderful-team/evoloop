"""
OutputChannelPolicy — 唯一的出站通道决策权威。

所有出站 payload（MessageBlock、TokenEvent、BaseEvent）的目标通道
在此处统一决定。Publisher 和 Bridge 只负责按给定 channels 搬运。

决策依据：
  - session_source: EvoContext.metadata.source（"voice" / "web" / "mobile" / ...）
                    由 current_session_source ContextVar 提供（engine.py 在节点启动时 set）
  - payload 类型
  - MessageBlock.status（streaming vs completed）
  - MessageBlock.tool_calls（值守场景：主 Agent 派活前的安抚回复）

单 Agent ReAct 架构下只有一个主 Agent 节点，不再按 node_source（supervisor/worker/finish）
区分通道；子代理执行体的消息由 ``resolve()`` 内按 ``task_type == "subagent"`` 整体屏蔽（R3）。

规则真值表（在此处集中维护，不散落各处）：

  | payload 类型       | status      | session_source | → channels            |
  |--------------------|-------------|----------------|-----------------------|
  | TokenEvent         | —           | voice          | {sse, voice}          |
  | TokenEvent         | —           | web/mobile/*   | {sse}                 |
  | ThinkingEvent      | —           | voice          | {sse, voice}          |
  | ThinkingEvent      | —           | web/mobile/*   | {sse}                 |
  | ProgressEvent      | —           | voice          | {sse, voice}          |
  | ProgressEvent      | —           | web/mobile/*   | {sse}                 |
  | AI MessageBlock    | streaming   | voice          | {sse, voice}          |
  | AI MessageBlock    | streaming   | web/mobile/*   | {sse}                 |
  | AI MessageBlock    | completed   | voice          | {sse, mobile, voice}  |
  | AI MessageBlock    | completed   | duty*          | {sse} 或 {sse, duty}（带委派调用=安抚）|
  | AI MessageBlock    | completed   | web/mobile/*   | {sse, mobile}         |
  | Tool MessageBlock  | streaming   | *              | {sse}                 |
  | Tool MessageBlock  | completed   | *              | {sse, mobile}         |
  | Human MessageBlock | completed   | mobile         | {sse}                 |
  | Human MessageBlock | completed   | web/*          | {sse, mobile}         |
  | BaseEvent (public) | —           | voice          | {sse, voice}          |
  | BaseEvent (public) | —           | web/mobile/*   | {sse}                 |
  | Other/unknown      | —           | *              | {sse}                 |

注意：
  - Tool / Human MessageBlock 默认也走 policy；如有特殊场景需要显式传入 channels，
    调用处必须注释说明为什么绕过 policy（当前仅剩 transient/error/HITL 消息需要）。
  - VoiceChannel 内部仍保留对非 voice source 的兜底过滤，作为 defense-in-depth。
"""

from __future__ import annotations

import contextvars
import logging

from app.core.engine.message.constants import MessageStatus
from app.core.engine.message.schemas import MessageBlock
from app.core.events.base import BaseEvent
from app.models.schemas.events import (
    ProgressEvent,
    ThinkingEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)

#: Thread-scoped session source ("voice"/"web"/"mobile") used by OutputChannelPolicy.
#: Set by AgentEngine.run_react_loop() from EvoContext.metadata.source.
current_session_source: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_source", default=None
)


def _is_voice_session(session_source: str | None) -> bool:
    return session_source == "voice"


def _is_duty_session(session_source: str | None) -> bool:
    """值守场景判定：委托统一的场景编码判定（app.core.channel.duty.is_duty_source）。"""
    from app.core.channel.duty import is_duty_source

    return is_duty_source(session_source)


def _has_delegation_call(block: object) -> bool:
    """判断 AI MessageBlock 是否携带委派工具调用（派活信号）。

    Agent 委派前会在同一条 assistant 消息里先输出安抚文本 + 附带委派工具
    调用（task）；据此精确识别「安抚回复」，避免把直接回复/最终回复（走
    SessionCompletedEvent）重复发送。
    """
    tool_calls = getattr(block, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
        if name == "task":
            return True
    return False


def _is_streaming_block(block: object) -> bool:
    return getattr(block, "status", "") in (MessageStatus.STREAMING, MessageStatus.RUNNING)


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
    ) -> set[str]:
        """
        Decide the target channels for an outbound payload.

        Args:
            payload:        The outbound object (MessageBlock, TokenEvent, BaseEvent, …).
            session_source: The session's origin ("voice", "web", "mobile", …).
                            Typically comes from ``current_session_source`` ContextVar.

        Returns:
            A set of channel names to deliver the payload to.
        """
        # Subagent 执行体的所有消息对用户通道不可见（R3）：subagent 是后台并行执行，
        # 不应出现在 voice/web/mobile 的消息流里。HITL 透传由父 Supervisor 在主会话发起。
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        if ctx and (ctx.metadata or {}).get("task_type") == "subagent":
            return set()

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
            if _is_duty_session(session_source):
                # 值守场景：仅「Supervisor 派活前的安抚文本」（AI + 带 route_to
                # 工具调用）路由到值守渠道发送给客户；直接回复/最终回复走
                # SessionCompletedEvent 订阅，避免重复。Worker 中间文本（
                # node_source=worker）不路由，防止内部过程泄漏给客户。
                # 用场景标识 "duty" 路由，publisher 端按渠道声明的 scenes
                # 匹配到具体值守渠道（如 wecom_duty）。
                if _is_supervisor(node_source) and _has_route_to_call(block):
                    return {"sse", "duty"}
                return {"sse"}
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
