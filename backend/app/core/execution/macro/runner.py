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
from app.utils.yaml import YAMLError, macro_from_yaml

logger = logging.getLogger(__name__)

_PARSE_ERRORS = (ValueError, OSError, RuntimeError, TypeError, KeyError, YAMLError)

# MacroScript 内存缓存：{macro_id: (updated_at_iso, MacroScript)}
_SCRIPT_CACHE: dict[int, tuple[str, MacroScript]] = {}
_MACRO_CACHE: dict[int, tuple[str, Macro]] = {}


def invalidate_macro_cache(macro_id: int | None = None) -> None:
    """清除 Macro 缓存。macro_id=None 时清除全部。"""
    if macro_id is not None:
        _SCRIPT_CACHE.pop(macro_id, None)
        _MACRO_CACHE.pop(macro_id, None)
    else:
        _SCRIPT_CACHE.clear()
        _MACRO_CACHE.clear()


def _get_cached_script(macro: Macro) -> MacroScript:
    """缓存解析后的 MacroScript，updated_at 变化时自动失效。"""
    cached = _SCRIPT_CACHE.get(macro.id)
    updated = macro.updated_at.isoformat() if macro.updated_at else ""
    if cached and cached[0] == updated:
        return cached[1]
    script = MacroScript.from_yaml(macro.macro_script)
    _SCRIPT_CACHE[macro.id] = (updated, script)
    if len(_SCRIPT_CACHE) > 500:
        _SCRIPT_CACHE.clear()
    return script


# load_macro 进程内缓存：{macro_id: (updated_at_iso, Macro)}
_MACRO_CACHE: dict[int, tuple[str, Macro]] = {}


async def load_macro(macro_id: int) -> Macro | None:
    cached = _MACRO_CACHE.get(macro_id)
    if cached is not None:
        return cached[1]
    from app.infrastructure.database import session_scope

    async with session_scope() as session:
        macro = await session.get(Macro, macro_id)
    if macro is not None:
        updated = macro.updated_at.isoformat() if macro.updated_at else ""
        _MACRO_CACHE[macro_id] = (updated, macro)
    return macro


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
    allowed_sources=frozenset({"desktop"}),
    # allowed_families 和 max_risk_tier 不限制 — 先跑通，后续迭代加安全
)


@dataclass
class ExecutionOutcome:
    ok: bool
    message: str
    fell_back: bool = False  # macro failed and an agentic recovery run took over


def is_navigation_macro(macro: Macro) -> str | None:
    """Check if macro is a frontend navigation. Returns route path or None."""
    info = get_navigation_info(macro)
    return info[0] if info is not None else None


def get_navigation_info(macro: Macro) -> tuple[str, str] | None:
    """Check if macro is a frontend navigation. Returns (route, feedback) or None."""
    # Guard against non-string scripts (drafts, mocks, or corrupted rows) to avoid
    # handing garbage/ MagicMock to yaml.safe_load, which can hang or recurse.
    script = macro.macro_script
    if not isinstance(script, str):
        return None
    try:
        steps = macro_from_yaml(script)
    except (YAMLError, ValueError, TypeError, AttributeError):
        return None
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, dict) and step.get("event_type") == "frontend_navigate":
            payload = step.get("payload", {})
            if isinstance(payload, dict):
                route = payload.get("route")
                if route:
                    feedback = ""
                    if macro.feedback:
                        feedback = macro.feedback
                    else:
                        feedback = payload.get("feedback", "")
                    return str(route), str(feedback)
    return None


def preflight(macro: Macro, params: dict[str, Any] | None) -> MacroScript:
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
        return _get_cached_script(macro)
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
    skip_activity_log: bool = False,
    skip_recording: bool = False,
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
        # Fast path: try optimized execution first (skip_activity_log + skip_recording).
        # Only fall back to self-healing (MacroService.run) on failure — the slow
        # self-heal path (activity log + recording + Agent recovery) is acceptable
        # for the error case, but must not penalize the success case.
        from app.core.execution.macro.engine import MacroEngine

        ok, msg, _data = await MacroEngine.execute(
            thread_id, script, params=params or {},
            skip_activity_log=skip_activity_log,
            skip_recording=skip_recording,
        )
        if ok:
            return ExecutionOutcome(True, msg or "")
        # Failure: trigger self-healing via MacroService (full overhead, acceptable on error)
        return await _run_with_self_heal(
            macro,
            thread_id=thread_id,
            script=script,
            params=params,
            project_id=project_id,
            skill_name=skill_name,
        )

    from app.core.execution.macro.engine import MacroEngine

    ok, msg, _data = await MacroEngine.execute(
        thread_id, script, params=params or {},
        skip_activity_log=skip_activity_log,
        skip_recording=skip_recording,
    )
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
