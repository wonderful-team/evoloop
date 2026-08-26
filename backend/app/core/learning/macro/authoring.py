"""Macro authoring — unified validation gate for Agent-authored macros.

Both create_macro (engine/tools/learning.py) and the update_macro rewrite path
(tools/update_macro.py) run the same pipeline: parse → cleanup → risk gate →
dry-run verification → risk tier. This module is the single home for that
pipeline so callers stop duplicating it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.learning.macro.schemas import (
    DEFAULT_ALLOWED_FAMILIES,
    MacroScript,
    compute_max_risk,
    scan_step_families,
)
from app.core.learning.macro.utils import cleanup_macro_steps, verify_macro_script

logger = logging.getLogger(__name__)


@dataclass
class ScriptValidation:
    """Result of the Agent-authored script gate."""

    ok: bool
    error: str | None = None
    cleaned_steps: list[dict[str, Any]] | None = None
    max_risk: str = "observe"
    requires_confirmation: bool = False
    _extra: dict[str, Any] = field(default_factory=dict, init=False)


async def validate_script(
    script_input: list[dict[str, Any]] | str,
    thread_id: str,
    project_id: int,
    allowed_families: set[str] = DEFAULT_ALLOWED_FAMILIES,
) -> ScriptValidation:
    """Parse, gate, dry-run, and score an Agent-authored macro script.

    Accepts a list of step dicts or a YAML string. Returns a ScriptValidation
    with ok=False and a human-readable error when any gate rejects the script.
    """
    try:
        if isinstance(script_input, str):
            from app.utils.yaml import macro_from_yaml

            steps = macro_from_yaml(script_input)
        else:
            steps = script_input
    except Exception as e:
        return ScriptValidation(ok=False, error=f"Invalid macro script: {e}")

    try:
        cleaned_steps, _ = cleanup_macro_steps(steps)
        script = MacroScript(steps=cleaned_steps)
    except Exception as e:
        return ScriptValidation(ok=False, error=f"Invalid macro script: {e}")

    reason = scan_step_families(script.steps, allowed_families)
    if reason:
        return ScriptValidation(ok=False, error=f"Risk gate rejected: {reason}")

    result = await verify_macro_script(
        cleaned_steps, thread_id=thread_id, _project_id=project_id
    )
    if not result.success:
        return ScriptValidation(
            ok=False, error=f"Macro verification failed: {result.error or result.status}"
        )

    max_risk = compute_max_risk(script.steps)
    return ScriptValidation(
        ok=True,
        cleaned_steps=cleaned_steps,
        max_risk=max_risk,
        requires_confirmation=max_risk in {"money", "escape"},
    )


def validate_macro_structure(
    macro_script: str | list[dict[str, Any]],
) -> tuple[bool, str, int]:
    """Lightweight structural validation of a macro script (no dry-run).

    Parses a YAML string or a list of step dicts into a MacroScript and
    reports step count. This is the cheap check used by API/display layers
    that only need to know whether the script is well-formed, without spinning
    up a browser. Returns (ok, error_or_empty, step_count).
    """
    try:
        script = (
            MacroScript.from_yaml(macro_script)
            if isinstance(macro_script, str)
            else MacroScript(steps=macro_script)
        )
    except Exception as e:
        return False, f"Invalid macro script: {e}", 0
    return True, "", len(script.steps)