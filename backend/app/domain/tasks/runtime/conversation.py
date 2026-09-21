"""值守对话直通（kf_ 线程）— 第三方客服消息的会话式处理。

商城客服（mcp_message 渠道）等会话类消息不进入任务队列（ProjectTask /
画布不可见），而是像企微值守（duty_ 线程）一样直接起会话推理：

    推送/poll → InboundMessageEvent → InboundMessageSubscriber 分流
    → dispatch_conversation_message（本模块）
      · 幂等：SharedState 持久化键（event_id 粒度，惰性过期）
      · 线程：kf_{project}_{contact}（多轮对话历史在引擎线程累积）
      · 并发：per-thread 锁保证同联系人次序；不同联系人并行
      · submit(await_completion=False)：事件驱动，不阻塞值守调度
    → SESSION_COMPLETED → KfReplyRouter 按 SharedState 路由元数据
      → OutboundReplyEvent → 渠道 send（mcp_reply 工具）

与任务队列车道彻底解耦：长任务跑多久都不影响客服响应时效。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 会话线程前缀：kf_{project}_{contact}。
# 与企微线 duty_ 前缀并列；provision._duty_thread_ids 依赖该前缀做
# 「停止值守 → 协作式切断」扫线，勿改命名。
THREAD_PREFIX = "kf_"

# 幂等键前缀与有效期（秒）。惰性过期：读取时超过有效期视为未处理并覆盖。
DEDUP_PREFIX = "mcp_kf_dedup"
DEDUP_TTL_SECONDS = 7 * 24 * 3600

# 路由元数据键：thread_id → {contact, channel, source_system, project_id}
ROUTE_PREFIX = "kf_route"

_thread_locks: dict[str, asyncio.Lock] = {}


def _lock_for(thread_id: str) -> asyncio.Lock:
    lock = _thread_locks.get(thread_id)
    if lock is None:
        lock = asyncio.Lock()
        _thread_locks[thread_id] = lock
    return lock


async def _seen_recently(event_id: str, source_system: str) -> bool:
    from app.core.state import shared_state

    key = f"{DEDUP_PREFIX}:{source_system}:{event_id}"
    try:
        raw = await shared_state.get(key, "")
        if raw:
            try:
                ts = float(raw)
                if time.time() - ts < DEDUP_TTL_SECONDS:
                    return True
            except (TypeError, ValueError):
                pass
        await shared_state.set(key, str(time.time()))
        return False
    except Exception:  # noqa: BLE001
        logger.exception("[kf_conversation] dedup check failed, fail-open")
        return False


async def dispatch_conversation_message(
    *,
    source_system: str,
    event_id: str,
    project_id: int,
    title: str,
    content: str,
    contact: str,
    channel: str,
) -> None:
    """一条客服消息 → kf_ 值守会话线程（不落任务，不占任务派发车道）。"""
    if await _seen_recently(event_id, source_system):
        logger.info(
            "[kf_conversation] deduped (server=%s, event=%s)",
            source_system,
            event_id,
        )
        return

    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.session.manager import session_manager
    from app.core.identity import identity_service
    from app.core.routing.dispatch_handler import command_router
    from app.core.state import shared_state

    thread_id = f"{THREAD_PREFIX}{project_id}_{contact}"
    message_text = content.strip() or title

    route_meta = {
        "contact": contact,
        "channel": channel,
        "source_system": source_system,
        "project_id": project_id,
    }
    try:
        from app.core.state import shared_state as _ss

        await _ss.set(f"{ROUTE_PREFIX}:{thread_id}", json.dumps(route_meta))
    except Exception:  # noqa: BLE001
        logger.exception("[kf_conversation] route meta persist failed")

    member_id = await identity_service.get_member_id() or 0

    # 客服会话补齐 intent_hint（skip_l0），与 web/mobile/wecom 入口同源。
    decision = await command_router.resolve(
        message_text,
        thread_id=thread_id,
        project_id=project_id,
        source="duty",
        skip_l0=True,
    )
    metadata: dict[str, Any] = {
        "source": "duty",
        "channel": channel,
        "channel_name": channel,
        "contact": contact,
        "reply_to": contact,
    }
    if decision.intent_hint:
        metadata["intent_hint"] = (
            decision.intent_hint.model_dump()
            if hasattr(decision.intent_hint, "model_dump")
            else decision.intent_hint
        )

    async with _lock_for(thread_id):
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=message_text,
            project_id=project_id,
            metadata=metadata,
            member_id=member_id,
            source="duty",
        )
        if result is None or getattr(result, "inputs", None) is None:
            logger.warning(
                "[kf_conversation] dispatch failed (thread=%s, event=%s)",
                thread_id,
                event_id,
            )
            return
        await session_manager.submit(
            thread_id,
            result.inputs,
            await_completion=False,
        )
        logger.info(
            "[kf_conversation] submitted (thread=%s, event=%s, contact=%s)",
            thread_id,
            event_id,
            contact,
        )
