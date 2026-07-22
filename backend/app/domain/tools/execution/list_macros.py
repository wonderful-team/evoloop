"""list_macros tool — Agent discovery for deterministic macros."""

import logging
from typing import Annotated

from app.core.engine.state.config import RunnableConfigMetadata
from app.core.execution.macro import lifecycle
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.list_macros")
async def list_macros(
    namespace: str | None = None,
    entity: str | None = None,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
    config: Annotated[dict | None, InjectedToolArg] = None,
) -> str:
    """List available deterministic macros (one-shot replay scripts).

    Use this tool to search for a verified macro that matches the current task.
    Pass a concise `query` that describes the action (e.g. 'open chrome',
    'login to github', 'submit expense report'). The tool searches macro
    names, descriptions, and trigger patterns.

    - `namespace`: Optional macro namespace (e.g. 'web/github', 'desktop/macos').
    - `entity`: Optional entity filter (e.g. 'github', 'chrome').
    - `query`: A short action description for substring search.
    - `limit`/`offset`: Pagination.

    **Important**: Check the `[params:]` field in results. If the macro lists
    required parameters, gather them all first before calling `run_macro`.
    Pass ALL parameters at once via `run_macro(macro_id, params={...})`.
    Never call `run_macro` without required params — it will fail.
    """
    meta = RunnableConfigMetadata.from_config(config or {})
    project_id = meta.project_id

    macros = await lifecycle.list_macros(
        project_id=project_id,
        status="verified",
        namespace=namespace,
        entity=entity,
        query=query,
        limit=limit,
        offset=offset,
    )

    # Context isolation: when no project is active, only global macros (project_id
    # is NULL) are visible to the Agent.  Project-scoped macros are never shown.
    if project_id is None:
        macros = [m for m in macros if m.project_id is None]

    if not macros:
        return ControllerResponse.success("No verified macros found.")

    lines = [f"Macro Catalog (showing {len(macros)} macros, offset {offset}):"]
    for m in macros:
        req = [p["name"] for p in (m.parameters or []) if p.get("required")]
        params_hint = f" [params: {', '.join(req)}]" if req else ""
        lines.append(f'#{m.id} — "{m.name}" — {m.description}{params_hint}')
    lines.append(
        "Hint: Check the [params:] field above. If the macro needs parameters, "
        "gather them all first (from user or context), then call "
        "run_macro(macro_id, params={name1: val1, name2: val2}) with ALL params at once. "
        "Do NOT call run_macro without required params."
    )
    return ControllerResponse.success("\n".join(lines))
