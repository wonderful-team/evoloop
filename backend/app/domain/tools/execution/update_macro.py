"""update_macro tool — Agent maintenance of deterministic macro metadata.

Allows the Agent to update a macro's name, description, trigger patterns,
parameter schema, and (with validation) its script. Script rewrites require a
rationale and will reset the macro to pending_review after passing the same
risk/verification gate used by create_macro.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.core.execution.macro import update_macro as lifecycle_update_macro
from app.core.execution.macro import load_macro
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


class UpdateMacroInput(DynamicBaseModel):
    macro_id: int = Field(..., description="ID of the macro to update.")
    name: str | None = Field(None, description="New macro name.")
    description: str | None = Field(None, description="New macro description.")
    trigger_patterns: list[str] | None = Field(
        None,
        description="New voice/text trigger patterns (e.g. ['快速会议', '创建会议']).",
    )
    parameters: list[dict] | None = Field(
        None,
        description="New parameter schema for the macro.",
    )


@evoloop_tool(
    args_schema=UpdateMacroInput,
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.update_macro",
)
async def update_macro(
    macro_id: int,
    name: str | None = None,
    description: str | None = None,
    trigger_patterns: list[str] | None = None,
    parameters: list[dict] | None = None,
) -> str:
    """Update macro metadata.

    Does NOT modify the macro script itself — only name, description,
    trigger patterns, and parameters. Use this to fix typos, improve
    discoverability, or adjust parameter requirements.
    """
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if trigger_patterns is not None:
        fields["trigger_patterns"] = trigger_patterns
    if parameters is not None:
        fields["parameters"] = parameters

    if not fields:
        return ControllerResponse.error(
            "No fields to update.",
            note="Provide at least one of: name, description, trigger_patterns, parameters.",
        )

    try:
        macro = await load_macro(int(macro_id))
        if macro is None:
            return ControllerResponse.error(f"Macro #{macro_id} not found.")

        ok = await lifecycle_update_macro(int(macro_id), fields)
        if not ok:
            return ControllerResponse.error(f"Failed to update macro #{macro_id}.")

        updated = ", ".join(fields.keys())
        return ControllerResponse.success(
            f"Macro #{macro_id} updated ({updated})."
        )
    except Exception as e:
        logger.exception("Failed to update macro %s: %s", macro_id, e)
        return ControllerResponse.error(f"Failed to update macro: {e}")
