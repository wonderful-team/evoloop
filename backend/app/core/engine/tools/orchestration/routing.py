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
    summary_template="evoloop.tool_summary.route_to")
def route_to(
    target: RoutingTarget,
    reason: str,
    context: RoutingContext | None = None,
    skill_ids: list[int] | None = None,
    workflow_mode: str = "single",
    session_goal: str | None = None,
) -> str:
    """
    [MANDATORY] Hand off the current task to a specialist node.

    ⚠️ CRITICAL: This tool MUST be called in EVERY Supervisor response.
    Outputting plain text without calling route_to will cause system failure.

    Available targets:
    - "worker": Universal executor for coding, file operations, and system control.
    - "deep_researcher": Web search and information gathering.
    - "documenter": Generate documentation, wiki, or README.
    - "chat": Ask questions or provide a direct response to the user.
    - "finish": Task completion or question fully answered.

    Args:
        target: The target specialist node. REQUIRED.
        reason: Why this handoff is occurring. REQUIRED.
        context: Structured guidance or attention focus for the specialist.
        skill_ids: List of skill IDs for multi-step workflows (executed in order).
        workflow_mode: "single" for one skill, "sequential" for step-by-step execution.
        session_goal: Optional session-level goal to establish or refine the active goal on the UI.
    """
    target_val = target.value
    from app.core.tools.registry import get_tool_bundle

    ctx = context or RoutingContext()
    context_dict = ctx.model_dump()

    if skill_ids:
        context_dict["skill_ids"] = skill_ids
        context_dict["workflow_mode"] = workflow_mode

    context_str = json.dumps(context_dict, ensure_ascii=False)
    skill_info = f" | Skill IDs: {skill_ids}" if skill_ids else ""

    return f"ROUTE_SIGNAL|{target_val}|{reason}|{context_str}{skill_info}"
