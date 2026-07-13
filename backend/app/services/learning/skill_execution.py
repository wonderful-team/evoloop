"""Skill execution service — the single entry point for running a skill.

Both the REST execute endpoint and the voice executor run deterministic
skills through ``run_deterministic``; the ONLY behavioral difference between
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

from app.core.execution.macro.schemas import MacroScript
from app.core.learning.skill_visibility import is_routable
from app.models.learning import LearnedSkill
from app.services.learning.skill_lifecycle import missing_required_params
from app.utils.yaml import YAMLError

logger = logging.getLogger(__name__)

_PARSE_ERRORS = (ValueError, OSError, RuntimeError, TypeError, KeyError, YAMLError)


class SkillGateError(Exception):
    """Synchronous gate rejection; ``code`` maps to per-transport responses."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExecutionPolicy:
    allow_self_heal: bool
    allowed_sources: frozenset[str] | None = None  # None = unrestricted


WEB_POLICY = ExecutionPolicy(allow_self_heal=True)
VOICE_POLICY = ExecutionPolicy(
    allow_self_heal=False, allowed_sources=frozenset({"desktop"})
)


@dataclass
class ExecutionOutcome:
    ok: bool
    message: str
    fell_back: bool = False  # macro failed and an agentic recovery run took over


async def load_skill(skill_id: int) -> LearnedSkill | None:
    from app.infrastructure.database import session_scope

    async with session_scope() as session:
        return await session.get(LearnedSkill, skill_id)


def preflight(
    skill: LearnedSkill,
    params: dict[str, Any] | None,
    execution_mode: str | None = None,
) -> MacroScript | None:
    """Shared gates; returns the parsed macro for deterministic skills.

    ``execution_mode`` overrides ``skill.execution_mode`` when given (the
    editor's debug-run passes the page-state mode). Returns None for skills
    that should run agentically.
    """
    if not is_routable(skill):
        raise SkillGateError(
            "not_routable",
            f"Skill is not active (status: {skill.status}); confirm it before executing",
        )
    missing = missing_required_params(skill.parameters, params or {})
    if missing:
        raise SkillGateError(
            "missing_params", f"Missing required parameters: {', '.join(missing)}"
        )
    mode = execution_mode or skill.execution_mode
    if mode == "deterministic" and skill.macro_script:
        try:
            return MacroScript.from_yaml(skill.macro_script)
        except _PARSE_ERRORS as e:
            raise SkillGateError(
                "bad_macro", f"Failed to parse macro YAML: {e}"
            ) from e
    return None


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


async def run_deterministic(
    skill: LearnedSkill,
    *,
    thread_id: str,
    params: dict[str, Any] | None,
    project_id: int,
    script: MacroScript,
    policy: ExecutionPolicy,
) -> ExecutionOutcome:
    """Execute a deterministic macro under the given policy."""
    if policy.allowed_sources is not None:
        sources = _collect_sources(script.steps)
        unsupported = sources - policy.allowed_sources
        if sources and unsupported:
            return ExecutionOutcome(
                False, f"unsupported macro source for voice: {sorted(unsupported)}"
            )

    if policy.allow_self_heal:
        return await _run_with_self_heal(
            skill,
            thread_id=thread_id,
            script=script,
            params=params,
            project_id=project_id,
        )

    from app.core.execution.macro.engine import MacroEngine

    ok, msg, _data = await MacroEngine.execute(thread_id, script, params=params or {})
    return ExecutionOutcome(ok, msg or "")


async def _run_with_self_heal(
    skill: LearnedSkill,
    *,
    thread_id: str,
    script: MacroScript,
    params: dict[str, Any] | None,
    project_id: int,
) -> ExecutionOutcome:
    """MacroService run with the unified self-healing fallback (web policy)."""
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.execution.macro.service import MacroService
    from app.utils.template import render_template

    exec_params = dict(params or {})
    exec_params["_skill_id"] = skill.id
    exec_params["_skill_name"] = skill.name

    result = await MacroService.run(
        thread_id=thread_id, script_input=script, params=exec_params, skill=skill
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
    # The engine's fallback_context often only carries a screenshot path;
    # include the failure message so the healing agent knows WHAT failed.
    if result.get("message"):
        failure_context.setdefault("error_message", result["message"])
    fallback_msg = render_template(
        "core/learning/self_healing.prompt.j2",
        skill_name=skill.name,
        failure_context=failure_context,
    )
    dispatched = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=fallback_msg,
        project_id=project_id,
        model=skill.active_model,
        metadata={"goal_prefix": "[Self-Healing] "},
    )
    if dispatched.status == "failed":
        logger.error("[MacroFallback] Dispatch failed: %s", dispatched.error)
        return ExecutionOutcome(False, f"Self-healing dispatch failed: {dispatched.error}")

    await run_agent_background(thread_id, dispatched.inputs)
    return ExecutionOutcome(False, result.get("message") or "", fell_back=True)
