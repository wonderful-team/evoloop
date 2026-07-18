"""Macro execution service — the single entry point for running a macro.

Both the REST execute endpoint and the voice executor run deterministic
macros through ``run_deterministic``; the ONLY behavioral difference between
the two transports is the explicit ``ExecutionPolicy``:

- ``WEB_POLICY``: self-healing enabled (macro failure falls back to an
  agentic recovery run), all macro sources allowed.
- ``VOICE_POLICY``: no self-healing (fast failure, design §16.5 — a voice
  user must not wait through a silent agentic grind) and desktop-only macro
  sources (DOM/mobile macros cannot run headlessly).

Synchronous gates (routable status, required params, macro parse) live in
``preflight`` so each transport can map rejections to its own response
contract (HTTP 403/400/500 vs a failed voice.route_result push).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.execution.macro.schemas import (
    RISK_TIER_ORDER,
    MacroScript,
    action_family,
    action_risk,
)
from app.models.macro import Macro
from app.utils.parameters import missing_required_params
from app.utils.yaml import YAMLError

logger = logging.getLogger(__name__)

_PARSE_ERRORS = (ValueError, OSError, RuntimeError, TypeError, KeyError, YAMLError)


class MacroGateError(Exception):
    """Synchronous gate rejection; ``code`` maps to per-transport responses."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExecutionPolicy:
    allow_self_heal: bool
    allowed_sources: frozenset[str] | None = None  # None = unrestricted
    allowed_families: frozenset[str] | None = None  # None = unrestricted; "act","control","observe","escape"
    max_risk_tier: str | None = None  # None = unrestricted; ordered: observe<act<data<money<escape


WEB_POLICY = ExecutionPolicy(allow_self_heal=True)
VOICE_POLICY = ExecutionPolicy(
    allow_self_heal=False,
    allowed_sources=frozenset({"desktop", "dom"}),
    allowed_families=frozenset({"act", "control", "observe"}),
    max_risk_tier="data",
)


@dataclass
class ExecutionOutcome:
    ok: bool
    message: str
    fell_back: bool = False  # macro failed and an agentic recovery run took over


async def load_macro(macro_id: int) -> Macro | None:
    from app.infrastructure.database import session_scope

    async with session_scope() as session:
        return await session.get(Macro, macro_id)


def preflight(
    macro: Macro,
    params: dict[str, Any] | None,
) -> MacroScript:
    """Shared gates; returns the parsed macro for deterministic skills."""
    if not macro.is_routable():
        raise MacroGateError(
            "not_routable",
            f"Macro is not active (status: {macro.status}); confirm it before executing",
        )
    missing = missing_required_params(macro.parameters, params or {})
    if missing:
        raise MacroGateError(
            "missing_params", f"Missing required parameters: {', '.join(missing)}"
        )
    try:
        return MacroScript.from_yaml(macro.macro_script)
    except _PARSE_ERRORS as e:
        raise MacroGateError("bad_macro", f"Failed to parse macro YAML: {e}") from e


def _collect_sources(steps: list[Any]) -> set[str]:
    out: set[str] = set()
    for step in steps:
        src = getattr(step, "source", None)
        if src is not None:
            val = getattr(src, "value", src)
            out.add(str(val).lower())
        for attr in ("then_steps", "else_steps", "steps"):
            out |= _collect_sources(getattr(step, attr, None) or [])
    return out


def _scan_steps_risk(steps: list[Any], policy: ExecutionPolicy) -> str | None:
    """Recursively scan steps for disallowed families or excessive risk.

    Returns None if all steps pass, or a human-readable rejection reason.
    """
    for step in steps:
        family = action_family(step.type, getattr(step, "event_type", None))
        if (
            policy.allowed_families is not None
            and family not in policy.allowed_families
        ):
            return f"disallowed family '{family}'"
        if policy.max_risk_tier is not None:
            risk = action_risk(getattr(step, "event_type", None))
            if RISK_TIER_ORDER.get(risk, 0) > RISK_TIER_ORDER.get(
                policy.max_risk_tier, 0
            ):
                return f"risk '{risk}' exceeds max '{policy.max_risk_tier}'"
        for attr in ("then_steps", "else_steps", "steps"):
            nested = getattr(step, attr, None) or []
            reason = _scan_steps_risk(nested, policy)
            if reason:
                return reason
    return None


async def run_deterministic(
    macro: Macro,
    *,
    thread_id: str,
    params: dict[str, Any] | None,
    project_id: int,
    script: MacroScript,
    policy: ExecutionPolicy,
    skill_name: str | None = None,
) -> ExecutionOutcome:
    """Execute a deterministic macro under the given policy."""
    if policy.allowed_sources is not None:
        sources = _collect_sources(script.steps)
        unsupported = sources - policy.allowed_sources
        if sources and unsupported:
            return ExecutionOutcome(
                False, f"unsupported macro source for voice: {sorted(unsupported)}"
            )

    if policy.allowed_families is not None or policy.max_risk_tier is not None:
        reason = _scan_steps_risk(script.steps, policy)
        if reason:
            return ExecutionOutcome(False, f"policy gate rejected: {reason}")

    if policy.allow_self_heal:
        return await _run_with_self_heal(
            macro,
            thread_id=thread_id,
            script=script,
            params=params,
            project_id=project_id,
            skill_name=skill_name,
        )

    from app.core.execution.macro.engine import MacroEngine

    ok, msg, _data = await MacroEngine.execute(thread_id, script, params=params or {})
    return ExecutionOutcome(ok, msg or "")


async def _run_with_self_heal(
    macro: Macro,
    *,
    thread_id: str,
    script: MacroScript,
    params: dict[str, Any] | None,
    project_id: int,
    skill_name: str | None = None,
) -> ExecutionOutcome:
    """MacroService run with the unified self-healing fallback (web policy)."""
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.execution.macro.service import MacroService
    from app.utils.template import render_template

    exec_params = dict(params or {})
    exec_params["_macro_id"] = macro.id
    exec_params["_macro_name"] = macro.name
    exec_params["_skill_name"] = skill_name or macro.name

    result = await MacroService.run(
        thread_id=thread_id, script_input=script, params=exec_params, macro=macro
    )

    if result.get("status") != "fallback_required":
        return ExecutionOutcome(bool(result.get("success")), result.get("message") or "")

    if not result.get("allow_self_healing", True):
        logger.warning(
            "[%s] Macro failed, self-healing disabled (reason: %s)",
            thread_id,
            result.get("healing_disabled_reason", "unknown"),
        )
        return ExecutionOutcome(False, result.get("message") or "")

    logger.warning("[%s] Macro failed, triggering agentic fallback", thread_id)
    failure_context = dict(result.get("fallback_context") or {})
    if result.get("message"):
        failure_context.setdefault("error_message", result["message"])
    fallback_msg = render_template(
        "core/learning/self_healing.prompt.j2",
        skill_name=skill_name or macro.name,
        failure_context=failure_context,
    )
    dispatched = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=fallback_msg,
        project_id=project_id,
        model=None,
        metadata={"goal_prefix": "[Self-Healing] "},
    )
    if dispatched.status == "failed":
        logger.error("[MacroFallback] Dispatch failed: %s", dispatched.error)
        return ExecutionOutcome(False, f"Self-healing dispatch failed: {dispatched.error}")

    await run_agent_background(thread_id, dispatched.inputs)
    return ExecutionOutcome(False, result.get("message") or "", fell_back=True)
