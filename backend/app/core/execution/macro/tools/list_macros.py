"""list_macros tool — Agent discovery for deterministic macros."""

import logging
from typing import Annotated

from app.core.engine.state.config import RunnableConfigMetadata
from app.core.execution.macro import list_macros as list_macros_dao
from app.core.execution.macro import load_macro
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.list_macros")
async def list_macros(
    macro_id: int | None = None,
    namespace: str | None = None,
    entity: str | None = None,
    query: str | None = None,
    limit: int = 10,
    offset: int = 0,
    config: Annotated[dict | None, InjectedToolArg] = None,
) -> str:
    """List available deterministic macros (one-shot replay scripts).

    Use this tool to search for a verified macro that matches the current task.
    Pass a concise `query` that describes the action (e.g. 'open chrome',
    'login to github', 'submit expense report'). The tool searches macro
    names, descriptions, and trigger patterns.

    - `macro_id`: Look up a specific macro by ID to see its details and parameters.
    - `namespace`: Optional macro namespace (e.g. 'web/github', 'desktop/macos').
    - `entity`: Optional entity filter (e.g. 'github', 'chrome').
    - `query`: A short action description for substring search. Multiple keywords
      can be passed separated by spaces (e.g. 'open chrome', '腾讯会议 链接').
      The search is performed across macro names, descriptions, and trigger
      patterns; results matching more keywords are ranked higher. Each keyword
      matches as a substring independently.
    - `limit`/`offset`: Pagination.

    **Important**: Check the `[params:]` field in results. If the macro lists
    required parameters, gather them all first before calling `run_macro`.
    Pass ALL parameters at once via `run_macro(macro_id, params={...})`.
    Never call `run_macro` without required params — it will fail.
    """
    meta = RunnableConfigMetadata.from_config(config or {})
    project_id = meta.project_id

    # Specific macro lookup by ID
    if macro_id is not None:
        macro = await load_macro(macro_id)
        if macro is None or not macro.is_active or macro.status != "verified":
            return ControllerResponse.success(f"Macro #{macro_id} not found or inactive.")
        macros = [macro]
    else:
        macros = await list_macros_dao(
            project_id=project_id,
            status="verified",
            namespace=namespace,
            entity=entity,
            query=query,
            limit=limit,
            offset=offset,
        )

        # Context isolation: when no project is active, only global macros
        # (project_id is NULL or 0) are visible to the Agent.
        if project_id is None or project_id == 0:
            macros = [m for m in macros if m.project_id is None or m.project_id == 0]

    if not macros:
        return ControllerResponse.success("No verified macros found.")

    lines = [f"Macro Catalog (showing {len(macros)} macros, offset {offset}):"]
    for m in macros:
        params = m.parameters or []
        req = [p["name"] for p in params if p.get("required")]
        params_hint = f" [params: {', '.join(req)}]" if req else ""
        lines.append(f'#{m.id} — "{m.name}" — {m.description}{params_hint}')
        # 展示参数级说明（含语义/换算规则），Agent 依赖此理解如何正确传参。
        # 例：adjust_money 需先读 goods_money 再换算差值，否则传错基数。
        for p in params:
            p_desc = p.get("description") or ""
            p_type = p.get("type") or ""
            p_req = "必填" if p.get("required") else "可选"
            lines.append(f'    - {p["name"]} ({p_type}, {p_req}): {p_desc}')
    lines.append(
        "Hint: Check the [params:] field above. If the macro needs parameters, "
        "gather them all first (from user or context), then call "
        "run_macro(macro_id, params={name1: val1, name2: val2}) with ALL params at once. "
        "Do NOT call run_macro without required params."
    )
    return ControllerResponse.success("\n".join(lines))
