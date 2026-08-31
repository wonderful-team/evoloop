"""React engine `task` tool — unified delegation & A2A entry (OpenCode `tool/task.ts`).

§4.3 / §10.2.2：本地子代理、A2A 远程委派、A2A Worker 回传、远端设备发现
全部收敛到单一 ``task`` 工具：
- ``action='run'``（默认）：本地 spawn 子代理；传 ``remote={'agent_id': ...}`` 则
  A2A 远程委派并挂起主循环等回调恢复。
- ``action='complete'``：当前线程是 A2A 子任务时把结果回传给 Caller 并结束
  （替代原 ``complete_task`` 工具）。
- ``action='list_agents'``：列出可用的远端 Agent 设备（也可由系统提示词
  ``<available_agents>`` 索引提供，§4.3）。
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)

#: 子代理最大递归深度（防无限 task 递归，对齐 OpenCode 默认 subagent_depth=1）
#: 实际由子代理工具面不含 task 保证；此上限作为兜底护栏。
MAX_SUBAGENT_DEPTH = 1

@evoloop_tool(is_hidden=False)
async def task(
    action: Literal["run", "complete", "list_agents"] = "run",
    subagent_type: str | None = None,
    description: str | None = None,
    prompt: str | None = None,
    remote: dict | None = None,
    status: str | None = None,
    summary: str | None = None,
    attachments: list[str] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一委派/A2A 入口——通过一个工具发起、委派或完成 Agent 工作。

    When to use:
    - 需要并行执行多个独立子任务，或需要隔离上下文的长任务 → action='run' + subagent_type。
    - 本机无法完成（缺少设备/能力）且 <available_agents> 有在线远端 Agent → action='run'
      + remote={'agent_id': '<device_key>'}（主循环挂起等远端回调后自动恢复）。
    - 当前线程是 A2A 子任务、需把结果回传给调用方 → action='complete'（status/summary）。
    - 需要查看在线远端设备 → action='list_agents'。

    When NOT to use:
    - 读具体文件用 read / glob / grep 更快。
    - 单文件/小范围代码搜索直接用工具，不要派子代理。
    - 没有合适子代理类型时直接用工具。

    Usage notes:
    1. 尽量并行发起多个 task（单条消息多个 tool call）。
    2. 给子代理完整自包含的指令（它看不到父会话上下文）。
    3. 子代理完成后返回一条最终消息，由你合并呈现给用户。
    4. prompt 应说明期望子代理写代码还是只调研，以及如何验证。

    Args:
        action: run（默认，本地子代理或 A2A 远程委派）/ complete（A2A Worker 回传结果）/
                list_agents（列出在线远端 Agent 设备）。
        subagent_type: run + 本地模式时必填（explore / general / reviewer / researcher）。
        description: 任务短描述（3-5 词）。
        prompt: 给子代理/远端设备的完整自包含指令。
        remote: run + 远程模式时传 {"agent_id": "<available_agents> 中的 device_key"}。
        status: complete 模式，'success' | 'failed'。
        summary: complete 模式，结果摘要。
        attachments: complete 模式，要回传给 Caller 的本地文件路径列表。
    """
    from app.core.engine.tools.a2a import (
        complete_a2a_task,
        dispatch_a2a_task,
        list_available_agents,
    )

    if action == "complete":
        return await complete_a2a_task(
            status=status or "success", summary=summary or "", attachments=attachments or []
        )

    if action == "list_agents":
        return await list_available_agents()

    # action == "run"
    if remote and remote.get("agent_id"):
        # §4.3 A2A 远程委派：派发远端任务 → 挂起主循环等 A2A 回调恢复。
        # 回传真实 tool_call_id（database_logger 在工具执行前写入 ctx）与 attachments，
        # 使派发落库的 hitl_request 消息与 AI tool_call id 对齐，回调才能精确 close。
        from app.core.context.manager import ContextManager

        return await dispatch_a2a_task(
            target_device_key=remote["agent_id"],
            instruction=prompt or "",
            attachments=attachments or [],
            tool_call_id=ContextManager.current().current_tool_call_id,
        )

    # 子代理递归防护：当前会话若已是子代理且深度达上限，拒绝再 spawn（对齐
    # OpenCode subagent-permissions 默认 deny task）。
    _meta = (config or {}).get("metadata") or {}
    _depth = int(_meta.get("subagent_depth") or 0)
    if _depth >= MAX_SUBAGENT_DEPTH:
        return (
            f"Error: 子代理递归深度已达上限（{MAX_SUBAGENT_DEPTH}），"
            "禁止再通过 task 派生子代理；请在父会话直接完成该子任务。"
        )

    from app.core.engine.react.subagent.spawner import spawn_subagent

    args = {
        "subagent_type": subagent_type or "general",
        "description": description or subagent_type or "general",
        "prompt": prompt or "",
        "remote": None,
    }
    result = await spawn_subagent(args, dict(config or {}))
    return str(result.get("content", ""))
