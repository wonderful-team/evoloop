"""Subagent background execution — lightweight Worker-primitive execution body.

A subagent is NOT a mini agent session (no own Supervisor/Finish nodes, no
intent round): the ticket already states the goal, so the body goes straight
into the Worker ReAct loop (same primitive as ``worker_rollout``). Design:
docs/subagent-design.md §4.1 / D2.5.

- Runs in its own ``activity_monitor.run_scope`` (independent run_id) so it
  does not clash with the parent run or sibling subagents.
- Reads a snapshot of the parent context; never writes back to the parent thread.
- Supports HITL (ask_human / request_authorization): on ``AgentHumanInterrupt``
  the body exits cleanly, marks ``SubagentRun`` as ``awaiting_human``, publishes
  ``SubagentHITLRequestEvent`` so the parent Supervisor asks the user, and later
  resumes from a rebuilt state (same primitive as normal HITL resume).
- Returns the final result TEXT (the Worker's final assistant report).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.schemas import RolloutOutcome
from app.core.exceptions import (
    AgentCancelledException,
    AgentHumanInterruptException,
)
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


async def run_subagent_background(
    thread_id: str,
    inputs: BackgroundAgentInputs | dict[str, Any],
) -> str:
    """Execute the Worker ReAct loop for a subagent; return the final result text."""
    if isinstance(inputs, dict):
        inputs = BackgroundAgentInputs(**inputs)

    project_id = inputs.project_id
    from app.constants import DEFAULT_PROJECT_ID

    if project_id is None:
        project_id = DEFAULT_PROJECT_ID

    task_type = inputs.metadata.get("task_type") if inputs.metadata else None

    try:
        async with activity_monitor.run_scope(
            thread_id, inputs.goal, task_type=task_type, project_id=project_id
        ) as run_id:
            return await _run_subagent_worker(thread_id, inputs, project_id, run_id)
    except AgentHumanInterruptException:
        # HITL request already registered; the body exits cleanly. The parent
        # will resume it later via run_subagent_background(hitl_resume_response=...).
        logger.info(
            f"[Subagent] {thread_id} interrupted (HITL), exits for parent routing."
        )
        return ""
    except AgentCancelledException:
        logger.info(f"[Subagent] {thread_id} cancelled")
        return ""


async def _run_subagent_worker(
    thread_id: str,
    inputs: BackgroundAgentInputs,
    project_id: int,
    run_id: str,
) -> str:
    from app.core.engine.runner_base import (
        build_agent_state,
        build_ctx,
        build_execution_config,
    )

    ctx = await build_ctx(thread_id, inputs, run_id=run_id)
    config = build_execution_config(thread_id, project_id, inputs, run_id, ctx)
    agent_state = await build_agent_state(thread_id, inputs)

    # 把 subagent 身份元数据写进 ctx.metadata（HITL 透传与事件路由依赖：
    # mark_subagent_awaiting_human_and_publish 用 task_type/parent_thread_id 判定）。
    for key in ("task_type", "subagent_id", "parent_thread_id", "root_thread_id"):
        if inputs.metadata and inputs.metadata.get(key):
            setattr(ctx.metadata, key, inputs.metadata[key])

    from app.core.engine.context_hydrator import AgentContextHydrator

    lc_config = {
        "configurable": config["configurable"],
        "metadata": config["metadata"],
    }
    await AgentContextHydrator.hydrate(
        ctx=ctx,
        state=agent_state,
        config=lc_config,
        last_human_msg=inputs.session_goal or "",
        is_retry=inputs.is_retry,
        iteration_count=inputs.iteration_count,
    )

    if inputs.hitl_resume_response:
        from app.core.hitl.orchestrator import HITLOrchestrator

        await HITLOrchestrator.resume_and_persist(
            thread_id=thread_id,
            project_id=project_id,
            member_id=ctx.member_id,
            config=config,
            user_input=inputs.hitl_resume_response,
            state=agent_state,
        )

    # Worker-primitive loop (same as worker_rollout): straight into Worker.
    from app.core.engine.background_agent.worker_rollout import run_worker_rollout

    outcome = await run_worker_rollout(agent_state, config, thread_id)

    # Extract the final result text from the Worker's last assistant_response.
    result_text = _extract_final_result(agent_state)

    if outcome == RolloutOutcome.INTERRUPTED:
        # HITL 透传：标记 SubagentRun awaiting_human + 发布事件给父（见 subagent_hitl.py）
        from app.core.engine.nodes.utils.subagent_hitl import (
            mark_subagent_awaiting_human_and_publish,
        )

        await mark_subagent_awaiting_human_and_publish(thread_id)
        return result_text or ""

    if outcome == RolloutOutcome.FAILED:
        # worker_rollout 会吞掉执行异常并返回 outcome=failed（配额耗尽、LLM 错误等）。
        # 必须在这里抛出，done_callback 的 task.exception() 才能把 SubagentRun 标为 failed，
        # 否则会出现 "执行失败但标记 completed" 的假成功。
        logger.error(
            f"[Subagent] {thread_id} worker outcome=failed; raising for terminal status"
        )
        raise RuntimeError(f"Subagent worker failed (outcome=failed): {thread_id}")

    logger.info(f"[Subagent] {thread_id} finished outcome={outcome}")
    return result_text or ""


def _extract_final_result(state: Any) -> str:
    """Extract the Worker's final assistant report text from state.messages."""
    for msg in reversed(state.messages or []):
        if getattr(msg, "role", None) == "assistant" and not getattr(
            msg, "tool_calls", None
        ):
            content = str(getattr(msg, "content", "") or "").strip()
            if len(content) > 20:
                return content
    return ""
