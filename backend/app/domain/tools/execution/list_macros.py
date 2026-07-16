"""list_macros tool — Agent discovery for deterministic macros."""

import logging

from app.core.execution.macro import lifecycle
from app.core.tools import evoloop_tool
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.list_macros")
async def list_macros(namespace: str | None = None, query: str | None = None) -> str:
    """List available deterministic macros (one-shot replay scripts).
    Macros are NOT SOPs: call run_macro(macro_id, params) to execute them as a
    whole. Do NOT read them step-by-step."""
    macros = await lifecycle.list_macros(status="verified")

    if namespace:
        macros = [m for m in macros if (m.namespace or "") == namespace]
    if query:
        q = query.lower()
        macros = [
            m
            for m in macros
            if q in m.name.lower()
            or q in (m.description or "").lower()
            or any(q in str(t).lower() for t in (m.trigger_patterns or []))
        ]

    if not macros:
        return ControllerResponse.success("No verified macros available.")

    lines = [f"Macro Catalog (count: {len(macros)}):"]
    for m in macros:
        req = [p["name"] for p in (m.parameters or []) if p.get("required")]
        params_hint = f" [params: {', '.join(req)}]" if req else ""
        lines.append(f'#{m.id} — "{m.name}" — {m.description}{params_hint}')
    lines.append(
        "Hint: run_macro(macro_id, params) executes the whole script; "
        "ask_human first if required params are missing."
    )
    return ControllerResponse.success("\n".join(lines))
