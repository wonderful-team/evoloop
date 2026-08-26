"""delete_macro tool — Agent retirement of broken or obsolete macros.

Allows the Agent to remove a macro that is no longer usable, has been
superseded by a repaired version, or was created by mistake. Use with care.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.core.learning.macro import delete_macro as lifecycle_delete_macro
from app.core.learning.macro import load_macro
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


class DeleteMacroInput(DynamicBaseModel):
    macro_id: int = Field(..., description="ID of the macro to delete.")
    rationale: str = Field(
        ...,
        description="Required: why this macro should be deleted (e.g., 'replaced by repaired version', 'route returns 404').",
    )


@evoloop_tool(
    args_schema=DeleteMacroInput,
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.delete_macro",
)
async def delete_macro(macro_id: int, rationale: str) -> str:
    """Delete a macro by ID.

    Requires a rationale. Use this when:
    - A macro is permanently broken and a repaired version has been created.
    - A macro was created by mistake.
    - A macro targets a page/feature that no longer exists.

    Do NOT delete macros just because they returned empty results once.
    """
    try:
        macro = await load_macro(int(macro_id))
        if macro is None:
            return ControllerResponse.error(f"Macro #{macro_id} not found.")

        ok = await lifecycle_delete_macro(int(macro_id))
        if not ok:
            return ControllerResponse.error(f"Failed to delete macro #{macro_id}.")

        logger.info(
            "Agent deleted macro #%s: %s (rationale: %s)",
            macro_id,
            macro.name,
            rationale,
        )
        return ControllerResponse.success(f"Macro #{macro_id} ({macro.name}) deleted. Rationale: {rationale}")
    except Exception as e:
        logger.exception("Failed to delete macro %s: %s", macro_id, e)
        return ControllerResponse.error(f"Failed to delete macro: {e}")
