"""Subagent spawner for the React engine.

对齐 OpenCode `task` 工具：子代理 = 独立子会话（独立 thread_id / 独立
AgentState / 独立消息流），看不到父会话消息（隔离上下文）。父 Agent 收到
子代理的最终文本后自行聚合，无聚合 LLM 轮。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.engine.agent import BackgroundAgentInputs, run_agent_background
from app.utils.id import gen_uuid

from .types import SubagentType, resolve_subagent_type

logger = logging.getLogger(__name__)


async def spawn_subagent(args: dict, config: dict) -> Any:
    """spawn 一个子代理并等待其结果。

    返回一个 ToolMessage 风格的 dict，由拦截器直接注入消息流。
    """
    subagent_type = args.get("subagent_type") or args.get("agent") or "general"
    stype: SubagentType = resolve_subagent_type(subagent_type)
    description = args.get("description") or subagent_type
    prompt = args.get("prompt") or args.get("task") or ""

    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    parent_tid = ctx.thread_id or config.get("configurable", {}).get("thread_id", "thread")
    sub_tid = f"{parent_tid}-react-sub-{gen_uuid()[:6]}"

    # 子代理深度继承：父会话若是子代理（subagent_depth>0），则 +1 传给子代理，
    # 供 task 工具做递归防护。
    _parent_meta = config.get("metadata") or {}
    parent_depth = int(
        getattr(ctx.metadata, "subagent_depth", None)
        or _parent_meta.get("subagent_depth")
        or 0
    )

    inputs = BackgroundAgentInputs(
        messages=[{"type": "human", "content": prompt}],
        project_id=ctx.project_id,
        model=config.get("configurable", {}).get("model"),
        goal=description,
        session_goal=description,
        metadata={
            "initial_node": "react",
            "source": ctx.metadata.source or "",
            # 身份传递：子代理在 worker 侧 build_ctx 依赖 metadata["member_id"]
            # 恢复归属会员（按用户 workspace/沙箱隔离的前提）。
            "member_id": ctx.member_id or 0,
            "subagent_type": subagent_type,
            "is_subagent": True,
            "subagent_depth": parent_depth + 1,
            # 工具面 + 人格由子代理类型决定（对齐 OpenCode visibleTools + persona）
            "subagent_tools": list(stype.tools),
            "subagent_prompt": stype.prompt,
            # A2A/通道策略按 task_type=="subagent" 判定（R3 抑制、hitl 免打扰）
            "task_type": "subagent",
        },
    )

    # 子代理走单发执行（react 模式内部即 run_agent_loop）
    try:
        await run_agent_background(sub_tid, inputs)
    except Exception as e:
        logger.exception(f"[ReactTask] subagent {sub_tid} failed: {e}")

    # 读取子代理最终输出（DB 中该子会话的最后一条 assistant 文本）
    text = await _read_subagent_result(sub_tid)
    return {
        "content": f"[{subagent_type} subagent] {description}\n\n{text}",
        "name": "task",
        "tool_call_id": args.get("id") or gen_uuid(),
    }


async def _read_subagent_result(sub_tid: str) -> str:
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models import Message

    try:
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == sub_tid)
                .order_by(Message.sequence_number.desc())
                .limit(20)
            )
            rows = (await session.execute(stmt)).scalars().all()
        texts = [
            str(r.content or "")
            for r in rows
            if r.role in ("ai", "assistant") and r.content
        ]
        return texts[0] if texts else "（子代理未返回可见结果）"
    except Exception as e:
        logger.warning(f"[ReactTask] failed to read subagent result: {e}")
        return "（子代理结果读取失败）"
