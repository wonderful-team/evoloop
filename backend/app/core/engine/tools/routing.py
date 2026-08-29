"""
Routing tool — hands off tasks to specialist nodes.
"""

import json

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals import RoutingContext
from app.core.tools import evoloop_tool


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal routing signal, not user-facing,
    summary_template="evoloop.tool_summary.route_to",
)
def route_to(
    target: RoutingTarget,
    reason: str,
    context: RoutingContext | None = None,
    skill_ids: list[int] | None = None,
    workflow_mode: str = "single",
    session_goal: str | None = None,
    subtasks: list[dict] | None = None,
    needs_audit: bool = False,
) -> str:
    """
    [MANDATORY] Hand off the current task to a specialist node.

    ⚠️ CRITICAL: This tool MUST be called when a task requires specialist
    execution (coding, file operations, system control, web search).
    You may also respond directly in plain text for simple greetings,
    Q&A, status checks, or cancellations.

    Available targets:
    - "worker": Universal executor for coding, file operations, and system control.
    - "deep_researcher": Web search and information gathering.
    - "documenter": Generate documentation, wiki, or README.
    - "finish": Task completion or question fully answered.

    Args:
        target: The target specialist node. REQUIRED.
        reason: Why this handoff is occurring. REQUIRED.
        context: Structured guidance or attention focus for the specialist. It is a JSON object whose string-list fields (acceptance_criteria, constraints, focus_paths, dependencies) MUST always be JSON arrays, never a single string. Key fields:
            - topic: noun-phrase naming the action itself (e.g. "ship the order"), not its prep.
            - acceptance_criteria: JSON array of verifiable outcomes defining "done" (e.g. ["all pending orders cancelled and re-verified"]). Wrap every criterion in brackets.
            - constraints: JSON array of constraint strings (optional).
            - focus_paths: JSON array of file paths (optional).
        skill_ids: List of skill IDs for multi-step workflows (executed in order).
        workflow_mode: "single" for one skill, "sequential" for step-by-step execution.
        session_goal: Optional session-level goal to establish or refine the active goal on the UI.
        subtasks: OPTIONAL. **委派并行子任务的统一入口（决策者与执行者共用）**。
            When the task can be split into 2-5 independent, non-conflicting
            pieces that can run in parallel, pass the list here and the system
            runs them as parallel subagents. Each element:
            {
              "id": "sub-1",
              "instruction": "short self-contained instruction (what to do, scope, what to return)",
              "role": "Subagent",
              "focus_paths": ["path1"],
              "acceptance_criteria": ["verifiable outcome"]
            }
            The instructions MUST be self-contained (subagents share your context
            but must not depend on other subagents' work). Do NOT use this for
            simple or serial-dependent work.
            **执行者（Worker）注意**：你在执行中发现任务可并行时，调用本工具只应
            使用 `subtasks` 参数做并行委派；不要用 `target` 做节点路由（那是决策者的职责）。
        needs_audit: OPTIONAL bool (default False). **监察决策（默认不监察）**。
            Set True ONLY when the user explicitly asked to check/review the result,
            or the completed task clearly needs review (high-risk action). When True,
            the Worker's delivery is verified by the Reviewer against the
            acceptance_criteria before presenting; when False the result is
            presented directly without audit. Do NOT set True for routine work.

    Example:
        route_to(target="worker", reason="cancel all pending orders", context={
            "topic": "cancel pending orders",
            "acceptance_criteria": ["all pending orders cancelled and re-verified"],
            "constraints": ["only cancel status=pending orders"],
        })
    """
    target_val = target.value

    ctx = context or RoutingContext()
    context_dict = ctx.model_dump()

    if skill_ids:
        context_dict["skill_ids"] = skill_ids
        context_dict["workflow_mode"] = workflow_mode

    if needs_audit:
        context_dict["needs_audit"] = True

    context_str = json.dumps(context_dict, ensure_ascii=False)
    skill_info = f" | Skill IDs: {skill_ids}" if skill_ids else ""
    subtask_info = (
        f" | Subtasks: {json.dumps(subtasks, ensure_ascii=False)}" if subtasks else ""
    )
    session_info = f" | Session Goal: {session_goal}" if session_goal else ""

    return (
        f"ROUTE_SIGNAL|{target_val}|{reason}|{context_str}"
        f"{skill_info}{subtask_info}{session_info}"
    )
