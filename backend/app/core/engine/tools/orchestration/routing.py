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
    summary_template="database_logger.tool_summary.route_to")
def route_to(
    target: RoutingTarget,
    reason: str,
    context: RoutingContext | None = None,
    authorized_tools: list[str] | None = None,
    skill_id: int | None = None,
    skill_ids: list[int] | None = None,
    workflow_mode: str = "single",
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
        authorized_tools: Restricted set of tools if specific constraints are needed.
                          The Supervisor should select appropriate tools from the
                          Worker Baseline Capability Pool defined in agent_main.yaml.
                          For deep_researcher: ["search_web", "browser_control", ...]
                          For documenter: ["read_file", "write_file", "list_directory", ...]
        skill_id: (Legacy) Single skill ID for backward compatibility.
        skill_ids: List of skill IDs for multi-step workflows (executed in order).
        workflow_mode: "single" for one skill, "sequential" for step-by-step execution.
    """
    target_val = target.value

    ctx = context or RoutingContext()
    context_dict = ctx.model_dump()
    if authorized_tools:
        context_dict["authorized_tools"] = authorized_tools

    # 处理多技能工作流参数
    if skill_ids:
        context_dict["skill_ids"] = skill_ids
        context_dict["workflow_mode"] = workflow_mode
    elif skill_id:
        context_dict["skill_id"] = skill_id
        context_dict["workflow_mode"] = "single"

    context_str = json.dumps(context_dict, ensure_ascii=False)
    skill_info = f" | Skill ID: {skill_id}" if skill_id else ""
    if skill_ids:
        skill_info = f" | Skill IDs: {skill_ids}"
    tool_info = f" | Tools: {authorized_tools}" if authorized_tools else ""

    return f"ROUTE_SIGNAL|{target_val}|{reason}|{context_str}{skill_info}{tool_info}"
