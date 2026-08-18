"""read_macro tool — Agent introspection for deterministic macros.

Returns macro metadata only; the full YAML script is intentionally omitted
so the Agent cannot accidentally copy/paste or reproduce an untrusted script.
"""

from __future__ import annotations

import logging

from app.core.execution.macro import find_macro_by_name, load_macro
from app.core.tools import evoloop_tool
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.read_macro")
async def read_macro(
    macro_id: int | None = None,
    macro_name: str | None = None,
) -> str:
    """Read macro metadata (no script) by id or name.

    Use this when you need to check a macro's trigger patterns, parameters,
    risk tier, or confirmation requirements before running or updating it.
    The full macro script is not exposed.
    """
    if macro_id is None and macro_name is None:
        return ControllerResponse.error(
            "read_macro requires macro_id or macro_name",
            note="Use list_macros to discover available macros.",
        )

    try:
        if macro_id is not None:
            macro = await load_macro(int(macro_id))
        else:
            macro = await find_macro_by_name(macro_name)
    except Exception as e:
        logger.exception("Failed to load macro for read_macro: %s", e)
        return ControllerResponse.error(f"Failed to load macro: {e}")

    if macro is None:
        return ControllerResponse.success(
            f"Macro not found (id={macro_id}, name={macro_name})."
        )

    lines = [
        f"Macro #{macro.id}: {macro.name}",
        f"  Description: {macro.description or '(no description)'}",
        f"  Status: {macro.status}",
        f"  Active: {macro.is_active}",
        f"  Risk tier: {macro.risk_tier}",
        f"  Requires confirmation: {macro.requires_confirmation}",
        f"  Allow self-healing: {macro.allow_self_healing}",
        f"  Trigger patterns: {macro.trigger_patterns or []}",
        f"  Parameters: {macro.parameters or []}",
    ]
    return ControllerResponse.success("\n".join(lines))
