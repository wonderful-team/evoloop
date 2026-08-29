"""Subagent control tools — Supervisor can cancel subagents or query their progress.

Design: docs/subagent-design.md §8.1 / §6.3 / §6.4.
"""

import logging

from app.core.engine.nodes.utils.subagent_manager import (
    cancel_all_subagents as _cancel_all_subagents,
)
from app.core.engine.nodes.utils.subagent_manager import (
    cancel_subagent as _cancel_subagent,
)
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(is_hidden=True, summary_template="evoloop.tool_summary.cancel_subagent")
async def cancel_subagent(subagent_thread_id: str) -> str:
    """取消一个正在运行的 subagent。

    Args:
        subagent_thread_id: 要取消的 subagent 的 thread_id（来自 [CONTEXT UPDATE] 的
            Active Subagents 列表中的 thread_id 字段）。
    """
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    parent_tid = ctx.thread_id if ctx else ""
    if not parent_tid or not subagent_thread_id:
        return "Error: 缺少 parent thread_id 或 subagent_thread_id"

    ok = await _cancel_subagent(parent_tid, subagent_thread_id)
    return (
        f"Cancelled subagent {subagent_thread_id}"
        if ok
        else (f"Subagent {subagent_thread_id} not found or already terminal")
    )


@evoloop_tool(
    is_hidden=True, summary_template="evoloop.tool_summary.cancel_all_subagents"
)
async def cancel_all_subagents() -> str:
    """取消当前会话下所有正在运行的 subagent。"""
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    parent_tid = ctx.thread_id if ctx else ""
    if not parent_tid:
        return "Error: 缺少 parent thread_id"

    count = await _cancel_all_subagents(parent_tid)
    return f"Cancelled {count} subagent(s)"
