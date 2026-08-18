"""Operation map tools — navigate_operation / list_operation_paths (v3.1).

"宏即路径": a verified Macro.macro_script IS the operation path (ordered,
executable steps). Navigation = retrieve the matching macro + present its
steps for Agent-guided execution. Falls back to the existing run_macro for
direct execution and self-healing on failure — no path-graph layer.

Design ref: docs/ATLAS_OPERATION_PATH_MAP_DESIGN.md (§4).
"""

import logging
from typing import Annotated

from app.core.engine.state.config import RunnableConfigMetadata
from app.core.execution.macro import list_macros
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.utils.controller_response import ControllerResponse
from app.core.execution.macro import (
    MacroScript,
)

logger = logging.getLogger(__name__)

_STEP_DESCRIPTORS = {
    "navigate": "打开页面",
    "frontend_navigate": "前端跳转",
    "open_url": "打开页面",
    "open_app": "打开应用",
    "click": "点击",
    "type_text": "输入",
    "input": "输入",
    "key_press": "按键",
    "wait": "等待",
    "wait_for": "等待元素",
    "extract": "提取数据",
    "get_text": "读取文本",
    "ax_menu_press": "菜单操作",
    "ax_press": "界面操作",
    "ax_set_value": "写入",
    "applescript": "AppleScript",
    "run_js": "执行 JS",
    "bash": "执行命令",
    # Step type fallbacks (when event_type is absent)
    "action": "执行动作",
    "if": "条件判断",
    "loop": "循环",
    "control": "控制",
    "native": "原生操作",
}


def _describe_steps(macro) -> list[str]:
    """Human-readable ordered step list from a macro_script (YAML → steps)."""

    try:
        script = MacroScript.from_yaml(macro.macro_script)
        steps = script.steps
    except Exception as exc:
        logger.debug("[operation_map] macro %s script parse failed: %s", macro.id, exc)
        return []

    out: list[str] = []
    for s in steps:
        if getattr(s, "step_number", None) is None:
            continue
        event_type = getattr(s, "event_type", None) or ""
        label = _STEP_DESCRIPTORS.get(event_type, event_type)
        target = getattr(s, "target_selector", None)
        if not label:
            # Fall back to the step type (action/extract/if/loop) when no
            # event_type (e.g. extract steps carry extract_type in the raw
            # YAML which the MacroStep model does not retain).
            label = _STEP_DESCRIPTORS.get(str(getattr(s, "type", "")), str(getattr(s, "type", "")))
        if target:
            out.append(f"{s.step_number}. {label} ({target})")
        else:
            out.append(f"{s.step_number}. {label}")
    return out


@evoloop_tool(summary_template="evoloop.tool_summary.navigate_operation")
async def navigate_operation(
    operation: str,
    entity: str | None = None,
    config: Annotated[dict | None, InjectedToolArg] = None,
) -> str:
    """Given a business operation, return the matching verified macro with its
    ordered step sequence for Agent-guided navigation.

    Use when the user asks "how do I <operation>" or "navigate to <operation>".
    The macro's steps ARE the operation path — execute them via run_macro, or
    follow them step by step.

    Args:
        operation: The target operation description (e.g. '查看商品', '改价',
            '打开微信'). Searched against macro names, descriptions and
            trigger patterns.
        entity: Optional entity filter (e.g. 'goods').

    Returns:
        The matching verified macro's steps (or a candidate list when multiple
        match, or an honest 'no known macro' message).
    """
    meta = RunnableConfigMetadata.from_config(config or {})
    project_id = meta.project_id

    macros = await list_macros(
        project_id=project_id,
        status="verified",
        entity=entity,
        query=operation,
        limit=10,
    )
    if project_id is None or project_id == 0:
        macros = [m for m in macros if m.project_id is None or m.project_id == 0]
    if not macros:
        return ControllerResponse.success(
            f"没有找到与 '{operation}' 匹配的已验证宏。",
            note="可调用 train_project 训练该项目，或走 Agent 兜底执行。",
        )

    # Prefer an exact trigger-pattern hit over a fuzzy name/description match.
    exact = [
        m
        for m in macros
        if operation in (m.trigger_patterns or [])
        or operation == m.name
        or operation == m.entity
    ]
    primary = exact[0] if exact else macros[0]

    if len(macros) > 1 and not exact:
        lines = [f"'{operation}' 命中多个宏，请澄清目标："]
        for m in macros[:6]:
            lines.append(f"#{m.id} — {m.name} — {m.description}")
        return ControllerResponse.success("\n".join(lines))

    req = [p["name"] for p in (primary.parameters or []) if p.get("required")]
    steps = _describe_steps(primary)
    head = [
        f"已定位操作宏 #{primary.id}: {primary.name}",
        f"描述: {primary.description}",
    ]
    if req:
        head.append(f"需要参数: {', '.join(req)}")
    head.append("操作步骤:")
    head.extend(steps)
    head.append(
        f"执行: run_macro(macro_id={primary.id}, params={{{', '.join(req)}}})"
    )
    return ControllerResponse.success("\n".join(head))


@evoloop_tool(summary_template="evoloop.tool_summary.list_operation_paths")
async def list_operation_paths(
    entity: str | None = None,
    config: Annotated[dict | None, InjectedToolArg] = None,
) -> str:
    """List all verified operation paths (macros) of the current project.

    Shows which business operations have deterministic macro paths and which
    don't, so the Agent knows when to execute directly vs fall back to its own
    reasoning. Complements list_macros with a project-scoped directory view.
    """
    meta = RunnableConfigMetadata.from_config(config or {})
    project_id = meta.project_id

    macros = await list_macros(
        project_id=project_id,
        status="verified",
        entity=entity,
        limit=100,
    )
    if project_id is None or project_id == 0:
        macros = [m for m in macros if m.project_id is None or m.project_id == 0]
    if not macros:
        return ControllerResponse.success(
            "当前项目没有已验证的操作路径。",
            note="可调用 train_project 训练（源码调研 + 运行时验证修复）。",
        )

    lines = [f"已训练的操作路径（{len(macros)} 个已验证宏）:"]
    for m in macros:
        steps = _describe_steps(m)
        lines.append(
            f"#{m.id} — {m.name} — {m.description} "
            f"({len(steps)} 步)"
        )
    return ControllerResponse.success("\n".join(lines))
