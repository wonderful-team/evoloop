"""update_macro tool — Agent maintenance of deterministic macro metadata.

Allows the Agent to update a macro's name, description, trigger patterns,
parameter schema, and (with validation) its script. Script rewrites require a
rationale and will reset the macro to pending_review after passing the same
risk/verification gate used by create_macro.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.core.execution.macro import confirm_macro, downgrade_macro, load_macro
from app.core.execution.macro import update_macro as lifecycle_update_macro
from app.core.execution.macro.schemas import (
    DEFAULT_ALLOWED_FAMILIES,
    MacroScript,
    compute_max_risk,
    scan_step_families,
)
from app.core.execution.macro.utils import cleanup_macro_steps, verify_macro_script
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.controller_response import ControllerResponse
from app.utils.parameters import finalize_macro_parameters

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
    macro_script: str | None = Field(
        None,
        description="New YAML macro script. If provided, rationale is required and the macro will be re-verified and reset to pending_review.",
    )
    rationale: str | None = Field(
        None,
        description="Required when macro_script is provided: explain why the script is being rewritten and what was fixed.",
    )


async def _verify_new_script(
    macro_id: int,
    project_id: int,
    macro_script: str,
) -> tuple[bool, str, list[dict] | None]:
    """Parse, gate, and dry-run a rewritten macro script."""
    try:
        parsed = MacroScript.from_yaml(macro_script)
        steps = parsed.model_dump().get("steps", [])
    except Exception as e:
        return False, f"Invalid macro script: {e}", None

    cleaned, _ = cleanup_macro_steps(steps)

    try:
        MacroScript.model_validate({"steps": cleaned})
    except Exception as e:
        return False, f"Invalid macro script after cleanup: {e}", None

    reason = scan_step_families(cleaned, DEFAULT_ALLOWED_FAMILIES)
    if reason:
        return False, f"Risk gate rejected: {reason}", None

    result = await verify_macro_script(
        cleaned,
        thread_id=f"rewrite-{macro_id}",
        _project_id=project_id,
    )
    if not result.success:
        return (
            False,
            f"Macro verification failed: {result.error or result.status}",
            None,
        )

    return True, "", cleaned


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
    macro_script: str | None = None,
    rationale: str | None = None,
) -> str:
    """Update macro metadata and/or script.

    - Metadata changes (name/description/trigger_patterns/parameters) are applied directly.
    - Script changes require a `rationale`, pass risk/verification, and reset the macro
      to `pending_review` (inactive until reviewed).
    - If the macro script contains bash/native/applescript or run_js ACTION steps,
      the rewrite will be rejected.

    ## Evoloop macro authoring standard (MUST follow when rewriting a script)

    The `macro_script` is a YAML string with `version`, `metadata`, and `steps`.
    The same conventions as create_macro apply:

    1. **Navigate URLs must be absolute and use the `{{base_url}}` placeholder.**
       Relative paths fail verification with "Cannot navigate to invalid URL".
       Correct:
       ```yaml
       - type: action
         event_type: navigate
         payload:
           url: '{{base_url}}/shop.html#url=shop/goods/lists'
       ```

    2. **Placeholders only support plain variables** (`{{param}}` /
       `{{parameters.param}}`). Jinja filters/expressions are NOT supported;
       apply defaults inside JS instead.

    3. **run_js is allowed ONLY in EXTRACT steps** (as a function
       `() => {...}` returning JSON-serializable data). run_js as an ACTION
       step is rejected by the risk gate.

    4. **Loop/if conditions use this exact schema** (type `element_exists` /
       `element_visible` / `text_contains` + `target_selector`):
       ```yaml
       - type: loop
         condition:
           type: element_exists
           target_selector: '.layui-laypage-next:not(.layui-disabled)'
         steps:
           - type: extract
             event_type: run_js
             extract_type: run_js
             key: count
             payload:
               script: '() => JSON.stringify({ count: document.querySelectorAll(".row").length })'
         max_iterations: 5
       ```

    5. **step_number is auto-normalized**; duplicates and gaps are fixed by
       the engine during cleanup.

    6. **Parameterize thresholds** via `parameters` + `{{param}}` placeholders
       instead of hardcoding business values.
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

    if macro_script is not None:
        if not rationale:
            return ControllerResponse.error(
                "rationale is required when rewriting the macro script.",
                note="Explain what was wrong and how the new script fixes it.",
            )

        try:
            macro = await load_macro(int(macro_id))
            if macro is None:
                return ControllerResponse.error(f"Macro #{macro_id} not found.")
        except Exception as e:
            logger.exception("Failed to load macro %s for rewrite: %s", macro_id, e)
            return ControllerResponse.error(f"Failed to load macro: {e}")

        ok, msg, cleaned = await _verify_new_script(macro_id, macro.project_id, macro_script)
        if not ok:
            return ControllerResponse.error(msg)

        max_risk = compute_max_risk(cleaned)
        fields["macro_script"] = macro_script
        fields["risk_tier"] = max_risk
        fields["requires_confirmation"] = max_risk in {"money", "escape"}
        fields["allow_self_healing"] = True

        # Keep declared parameters if the caller provided them; otherwise
        # re-derive from the rewritten script so stale declarations (or
        # missing ones for new {{placeholders}}) never linger.
        if "parameters" not in fields:
            fields["parameters"] = finalize_macro_parameters(None, macro_script)

    if not fields:
        return ControllerResponse.error(
            "No fields to update.",
            note="Provide at least one of: name, description, trigger_patterns, parameters, macro_script.",
        )

    try:
        macro = await load_macro(int(macro_id))
        if macro is None:
            return ControllerResponse.error(f"Macro #{macro_id} not found.")

        ok = await lifecycle_update_macro(int(macro_id), fields)
        if not ok:
            return ControllerResponse.error(f"Failed to update macro #{macro_id}.")

        script_note = ""
        if "macro_script" in fields:
            # No human review step exists for agent-authored rewrites: the
            # dry-run verification in _verify_new_script IS the gate. Reset to
            # pending_review first (invalidate any prior verified state), then
            # self-activate so the repaired macro stays discoverable.
            await downgrade_macro(int(macro_id))
            confirmed = await confirm_macro(int(macro_id))
            script_note = (
                " New script dry-run verified and re-activated."
                if confirmed else " Activation failed after rewrite; the macro is inactive — report this."
            )

        updated = ", ".join(fields.keys())
        return ControllerResponse.success(
            f"Macro #{macro_id} updated ({updated})." + script_note
        )
    except Exception as e:
        logger.exception("Failed to update macro %s: %s", macro_id, e)
        return ControllerResponse.error(f"Failed to update macro: {e}")
