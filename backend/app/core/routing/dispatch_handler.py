"""Unified dispatcher for chat and voice routes.

This module consolidates the previously duplicated routing logic in
``app.api.routes.agent.chat`` and ``app.api.routes.voice_ws``:

1. Normalize raw input into an ``IncomingMessage`` via an ``InputChannel``.
2. Run ``CommandRouter.resolve`` to get a ``RouteDecision``.
3. Store the ``intent_hint`` as a JSON-safe dict on the message metadata
   (the metadata is persisted before the engine hydrates it).
4. Dispatch any L0 hit through ``dispatch_decision`` + a channel presenter.
5. For L0 misses, return the normalized message and the ``dispatch_agent_run``
   inputs so the caller can start the agent background worker in the
   channel-appropriate way (HTTP ``BackgroundTasks`` for web,
   ``asyncio.create_task`` for voice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel
from app.core.context import EvoContext
from app.core.routing.actions import ActionOutcome, run_macro
from app.core.routing.command_router import CommandRouter
from app.core.routing.conversation_state import (
    _get_thread_last_macro_result,
    _set_thread_last_macro_result,
)
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import IntentHint
from app.core.routing.thread_locks import route_lock_scope

logger = logging.getLogger(__name__)

command_router = CommandRouter()
_routing_store = get_store()


@dataclass
class DispatchOutcome:
    """Outcome of a unified route dispatch attempt.

    - ``handled=True``: an L0/local route resolved the request.
      ``local_response`` holds the ``ActionOutcome`` containing the execution details.
    - ``handled=False``: the request must be delegated to the agent.
      ``msg`` is the normalized ``IncomingMessage`` and ``inputs`` is the
      value returned by ``InputChannel.dispatch`` (the agent run inputs).
    """

    handled: bool
    local_response: ActionOutcome | None = None
    msg: IncomingMessage | None = None
    inputs: Any = None


async def dispatch_user_message(
    raw: dict[str, Any],
    *,
    source: str,
    input_channel: InputChannel,
    thread_id: str,
    project_id: int,
    member_id: int,
    context: EvoContext,
    agent_run_registry: Any = None,
) -> DispatchOutcome:
    """Normalize, route, and dispatch a user message from any channel.

    The caller is responsible for holding the route lock and setting an active
    ``EvoContext`` (use ``route_lock_scope``). This function performs the
    channel-agnostic routing work.
    """
    msg = await input_channel.receive(raw, context=context, member_id=member_id)
    if msg is None:
        return DispatchOutcome(handled=False, msg=None)

    if not msg.source:
        msg.source = source
    if msg.project_id is None:
        msg.project_id = project_id
    if msg.member_id is None:
        msg.member_id = member_id

    decision = await command_router.resolve(
        msg.text,
        thread_id=thread_id,
        project_id=project_id,
        source=source,
        skip_l0=(source in ("web", "mobile")),
    )

    if decision.intent_hint:
        msg.metadata = msg.metadata or {}
        # The metadata dict is persisted to JSON before the engine hydrates it,
        # so keep the intent hint as a plain dict to avoid serialization errors.
        msg.metadata["intent_hint"] = (
            decision.intent_hint.model_dump()
            if isinstance(decision.intent_hint, IntentHint)
            else decision.intent_hint
        )

    target_type = decision.target_type

    if target_type == "agent":
        logger.info(
            "[dispatch] %s L0 miss for thread %s (intent=%s) → agent",
            source,
            thread_id,
            decision.intent_hint,
        )
        # [前置上下文] 注入只服务 voice：L0 宏/导航的执行结果摘要（last_macro_result）
        # 与滚动语音指令历史（session_history）只存在路由层内存、不落库，Agent 需要
        # 靠注入才能得知"上一轮语音指令做了什么"。web 文字消息跳过 L0，不执行任何
        # 宏/导航，注入反而会把同一线程内其他订单/会话的语音指令历史泄漏进当前消息
        # （实测串单：390 的 human 消息被注入 389 的退款上下文），因此 web 直接入 Agent。
        if source == "voice":
            parts: list[str] = []
            macro_result = _get_thread_last_macro_result(thread_id)
            if macro_result:
                parts.append(macro_result)
            session_history = (
                decision.intent_hint.session_history if decision.intent_hint else None
            )
            if session_history:
                previous = [h for h in session_history if h and h.strip()]
                if previous:
                    parts.append("刚执行过的语音指令：" + "；".join(previous))
            if parts:
                msg.text = "[前置上下文] " + "。".join(parts) + "\n" + msg.text
        inputs = await input_channel.dispatch(msg)
        return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    if target_type == "local":
        action = decision.target.get("action", "")
        args = decision.params
        route = (
            decision.target.get("route")
            if decision.target.get("type") == "navigate"
            else None
        )
        if route is not None:
            local_outcome = ActionOutcome(
                ok=True,
                message=_routing_store.responses["generic"]["ok"],
                action_type="navigate",
                data={"route": route},
            )
            logger.info(
                "[dispatch] %s L0 navigate handled for thread %s", source, thread_id
            )
            return DispatchOutcome(handled=True, local_response=local_outcome)
        else:
            if source == "voice":
                local_outcome = ActionOutcome(
                    ok=True,
                    message=_routing_store.responses["local"]["success"],
                    action_type="local",
                    data={"action": action, "args": args},
                )
                logger.info(
                    "[dispatch] %s L0 local action handled for thread %s",
                    source,
                    thread_id,
                )
                return DispatchOutcome(handled=True, local_response=local_outcome)
            else:
                logger.info(
                    "[dispatch] web local non-navigate action delegates to agent"
                )
                inputs = await input_channel.dispatch(msg)
                return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    if target_type == "macro":
        macro_id = decision.target.get("id")
        if not isinstance(macro_id, int):
            logger.warning("[dispatch] macro decision missing id: %s", decision)
            inputs = await input_channel.dispatch(msg)
            return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

        # 语音宏超时设 30s：登录/复杂宏（navigate + wait + 表单填充）常需 10-20s，
        # 10s 会误判超时下沉 Agent（宏仍在后台执行，登录实际成功），造成错乱。
        macro_timeout = 30.0 if source == "voice" else None
        outcome = await run_macro(
            macro_id,
            decision.params,
            thread_id=thread_id,
            project_id=project_id,
            source=source,
            timeout=macro_timeout,
            agent_run_registry=agent_run_registry,
        )
        handled = True
        if source == "voice" and outcome.action_type != "navigate" and not outcome.ok:
            handled = False
            # 宏执行失败 → 委托 Agent 继续完成，附上失败上下文，
            # 避免 Agent 不知道宏执行到哪、为什么失败而从头重来。
            name = (
                outcome.data.get("macro_name")
                or f"宏#{outcome.data.get('macro_id', '')}"
            )
            failure = outcome.message or "宏执行失败"
            if msg.text and failure:
                msg.text = (
                    f"{msg.text}\n\n"
                    f"[宏执行失败] 已尝试执行宏「{name}」但失败：{failure}。"
                    f"请基于该上下文继续完成用户请求，不要重复用户已失败的尝试。"
                )

        if handled:
            # L0 宏执行成功不持久化到 DB，Agent 无从得知。记录结果摘要到
            # per-thread L0 上下文，供下一轮 L0 miss → agent 时注入。
            if outcome.ok:
                summary = _summarize_macro_success(outcome)
                if summary:
                    _set_thread_last_macro_result(thread_id, summary)
            return DispatchOutcome(handled=True, local_response=outcome)
        else:
            inputs = await input_channel.dispatch(msg)
            return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    logger.warning("[dispatch] unknown target_type: %s", target_type)
    inputs = await input_channel.dispatch(msg)
    return DispatchOutcome(handled=False, msg=msg, inputs=inputs)


def _summarize_macro_success(outcome: ActionOutcome) -> str:
    """Build a short summary of a successful L0 macro execution for Agent context.

    Navigation-type outcomes (e.g. "跳转到添加商品页") carry the route in
    ``data``; regular macro outcomes carry ``macro_name`` + the response message.
    Falls back to the macro name when the response text is uninformative.
    """
    data = outcome.data or {}
    if outcome.action_type == "navigate":
        route = data.get("route") or ""
        feedback = data.get("feedback") or ""
        return f"已跳转导航：{feedback or route or '目标页面'}"
    macro_name = data.get("macro_name") or "宏"
    message = (outcome.message or "").strip()
    store = _routing_store
    success_resp = (
        store.responses.get("macro", {}).get("success", "") if store else ""
    ) or ""
    if not message or message == success_resp:
        return f"已执行宏「{macro_name}」"
    return f"已执行宏「{macro_name}」：{message}"


__all__ = [
    "DispatchOutcome",
    "dispatch_user_message",
    "route_lock_scope",
    "command_router",
]
