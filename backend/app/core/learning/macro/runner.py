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

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import app.core.learning.constants as _mc
from app.core.learning.constants import (
    RUN_RESULT_FALLBACK_REQUIRED,
    ExecutionPolicy,
)
from app.core.learning.macro.engine import MacroEngine
from app.core.learning.macro.lifecycle import (
    invalidate_macro_cache as _invalidate_lifecycle_cache,
)
from app.core.learning.macro.lifecycle import load_macro as _load_macro
from app.core.learning.macro.schemas import (
    RISK_TIER_ORDER,
    MacroScript,
    action_risk,
    iter_macro_steps,
)
from app.core.project.utils import get_project_path, read_project_json
from app.infrastructure.config.vault import SecureVaultService
from app.models.macro import Macro
from app.utils.parameters import missing_required_params
from app.utils.yaml import YAMLError, macro_from_yaml

logger = logging.getLogger(__name__)

_PARSE_ERRORS = (ValueError, OSError, RuntimeError, TypeError, KeyError, YAMLError)


def invalidate_macro_cache(macro_id: int | None = None) -> None:
    """No-op cache invalidation（宏缓存已移除，见 lifecycle.invalidate_macro_cache）。"""
    _invalidate_lifecycle_cache(macro_id)


def _get_cached_script(macro: Macro) -> MacroScript:
    """解析宏脚本为 MacroScript（无缓存：每次执行读最新脚本）。

    历史实现有进程内缓存（_SCRIPT_CACHE），因 update_macro 未失效缓存导致
    "DB 已更新但执行旧脚本" 问题，已移除。宏脚本每次执行直接解析。
    """
    return MacroScript.from_yaml(macro.macro_script)


async def load_macro(macro_id: int) -> Macro | None:
    """加载 Macro（带进程内缓存，实现在 lifecycle）。"""
    return await _load_macro(macro_id)


class MacroGateError(Exception):
    """Synchronous gate rejection; ``code`` maps to per-transport responses."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ExecutionPolicy / WEB_POLICY / VOICE_POLICY live in constants.py so other
# modules can reference them without importing the full runner.


@dataclass
class ExecutionOutcome:
    ok: bool
    message: str
    fell_back: bool = False  # macro failed and an agentic recovery run took over
    extracted_data: dict[str, Any] | None = None  # data captured by EXTRACT steps
    step_log: list[dict[str, Any]] | None = None  # per-step execution records
    execution_warnings: list[str] | None = (
        None  # non-fatal signals (e.g. zero-iteration loop)
    )


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
        if isinstance(step, dict) and step.get("event_type") == _mc.FRONTEND_NAVIGATE:
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


def extract_navigation_url(macro: Macro) -> str | None:
    """Extract the navigation URL from a macro script, if any.

    Handles both navigation step shapes: ``frontend_navigate`` (route field)
    and ``navigate``/``goto`` (url field). Callers that previously hand-rolled
    ``re.search(r"url:\\s*(\\S+)", macro.macro_script)`` should use this
    instead of parsing the raw YAML themselves.
    """
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
        if not isinstance(step, dict):
            continue
        payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
        event_type = str(step.get("event_type") or "")
        if event_type == _mc.FRONTEND_NAVIGATE:
            route = payload.get("route")
            if route:
                return str(route)
        elif event_type in (_mc.NAVIGATE, _mc.GOTO):
            url = payload.get("url")
            if url:
                return str(url)
    return None


def preflight(macro: Macro, params: dict[str, Any] | None) -> MacroScript:
    """Shared gates; returns the parsed macro for deterministic skills."""
    if not macro.is_routable():
        raise MacroGateError(
            "not_routable",
            f"Macro is not active (status: {macro.status}); confirm it before executing",
        )
    params = params or {}
    missing = missing_required_params(macro.parameters, params)
    if missing:
        # 缺参时尝试从 Secure Vault 自动补参：按参数名匹配当前项目凭据字段。
        # 例：宏缺 username/password → 从凭据 payload 的 username/password 字段填充，
        # 避免 L0 命中后因缺参失败下沉 Agent、或向用户索要已录入密码箱的账号。
        vault_fill_params(macro, missing, params)
        still_missing = missing_required_params(macro.parameters, params)
        if still_missing:
            raise MacroGateError(
                "missing_params",
                f"Missing required parameters: {', '.join(still_missing)}",
            )
    try:
        return _get_cached_script(macro)
    except _PARSE_ERRORS as e:
        raise MacroGateError("bad_macro", f"Failed to parse macro YAML: {e}") from e


async def resolve_project_base_url(project_id: int | None) -> str | None:
    """从项目配置（project.json 的 url 字段）解析宏的 {{base_url}} 注入值。

    L0（routing/actions.py）和引擎侧（domain/tools/execution/macro.py）都依赖
    {{base_url}} 导航到项目后台页面；统一在此解析，避免两处重复实现漂移。
    """
    if not project_id:
        return None
    try:
        proj_path = await get_project_path(project_id)
        if proj_path:
            pj = read_project_json(proj_path)
            return pj.get("url")
    except (OSError, ValueError):
        logger.warning(
            "[Macro] failed to resolve project url for project %s",
            project_id,
            exc_info=True,
        )
    return None


def vault_fill_params(macro: Macro, missing: list[str], params: dict[str, Any]) -> int:
    """尝试从 Secure Vault 按参数名补全缺失参数，返回补全数量。"""
    filled = 0
    try:
        credentials = SecureVaultService.list_credentials(project_id=macro.project_id)
        for name in list(missing):
            if name in params:
                continue
            for cred in credentials:
                if cred.get("project_id") not in (None, macro.project_id):
                    continue
                try:
                    payload = SecureVaultService.get_credential_payload(
                        cred["identifier"], project_id=macro.project_id
                    )
                except (KeyError, PermissionError):
                    continue
                if name in payload:
                    params[name] = str(payload[name])
                    filled += 1
                    break
    except Exception:
        logger.warning(
            "[Macro] vault auto-fill failed for %s", macro.name, exc_info=True
        )
    return filled


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


def _step_requires_ui(step: Any) -> bool:
    """True if the step needs a non-desktop UI surface (browser/phone).

    Utility and control-flow steps (wait/wait_for, IF/LOOP, native/bash) run
    without any UI, so their source label (which defaults to DOM) must not gate
    headless voice execution.
    """
    step_type = getattr(step, "type", None)
    st = str(getattr(step_type, "value", step_type)).lower() if step_type else ""
    if st in (_mc.NATIVE, _mc.BASH):
        return False
    if st in (_mc.CONTROL, _mc.IF, _mc.LOOP):
        return False
    event = getattr(step, "event_type", None)
    et = str(getattr(event, "value", event)).lower() if event else ""
    if et in (_mc.WAIT, _mc.WAIT_FOR):
        return False
    return True


def _scan_steps_risk(steps: list[Any], policy: ExecutionPolicy) -> str | None:
    """Scan a macro step tree (MacroStep or dict) for policy violations.

    Returns None if all steps pass, or a human-readable rejection reason.
    """
    for family, _step_type, event_type in iter_macro_steps(steps):
        if (
            policy.allowed_families is not None
            and family not in policy.allowed_families
        ):
            return f"disallowed family '{family}'"
        if policy.max_risk_tier is not None:
            risk = action_risk(event_type)
            if RISK_TIER_ORDER.get(risk, 0) > RISK_TIER_ORDER.get(
                policy.max_risk_tier, 0
            ):
                return f"risk '{risk}' exceeds max '{policy.max_risk_tier}'"
    return None


async def _execute_engine(
    thread_id: str,
    script: MacroScript,
    params: dict[str, Any] | None,
    *,
    skip_activity_log: bool,
    skip_recording: bool,
) -> tuple[bool, str, dict[str, Any] | None, dict[str, Any]]:
    """Run the MacroEngine once; shared by all policy branches."""
    extracted_data: dict[str, Any] = {}
    ok, msg, data = await MacroEngine.execute(
        thread_id,
        script,
        params=params or {},
        extracted_data=extracted_data,
        skip_activity_log=skip_activity_log,
        skip_recording=skip_recording,
    )
    return ok, msg, data, extracted_data


async def run_deterministic(
    macro: Macro,
    *,
    thread_id: str,
    params: dict[str, Any] | None,
    project_id: int,
    script: MacroScript,
    policy: ExecutionPolicy,
    skip_activity_log: bool = False,
    skip_recording: bool = False,
) -> ExecutionOutcome:
    """Execute a deterministic macro under the given policy."""
    if policy.allowed_sources is not None:
        # Only UI-bound steps carry a meaningful execution-source requirement.
        # Utility/control steps (wait, IF/LOOP, native/bash) are headless-safe
        # even when their source label defaults to DOM, so they must not be
        # rejected for voice.
        ui_steps = [s for s in script.steps if _step_requires_ui(s)]
        sources = _collect_sources(ui_steps)
        unsupported = sources - policy.allowed_sources
        if sources and unsupported:
            return ExecutionOutcome(
                False, f"unsupported macro source for voice: {sorted(unsupported)}"
            )

    if policy.allowed_families is not None or policy.max_risk_tier is not None:
        reason = _scan_steps_risk(script.steps, policy)
        if reason:
            return ExecutionOutcome(False, f"policy gate rejected: {reason}")

    ok, msg, data, extracted_data = await _execute_engine(
        thread_id,
        script,
        params,
        skip_activity_log=skip_activity_log,
        skip_recording=skip_recording,
    )

    if not ok and policy.allow_self_heal:
        # Fast path: optimized execution first (skip_activity_log + skip_recording).
        # Only fall back to self-healing (MacroService.run) on failure — the slow
        # self-heal path (activity log + recording + Agent recovery) is acceptable
        # for the error case, but must not penalize the success case.
        outcome = await _run_with_self_heal(
            macro,
            thread_id=thread_id,
            script=script,
            params=params,
            project_id=project_id,
        )
        # 自愈路径未带回 step_log 时，用 fast path 已收集的 step_log 兜底，
        # 保证 Agent 在失败场景也能拿到步骤级诊断（步骤号/成败/错误）。
        if not outcome.step_log and data:
            outcome.step_log = (data or {}).get("step_log")
        return outcome

    # 失败时把失败步骤信息并入 message，委托 Agent 时传递失败上下文
    if not ok and data and data.get("step_number"):
        step_note = (
            f"第{data.get('step_number')}步({data.get('event_type') or 'action'})失败"
        )
        msg = f"{step_note}: {msg}" if msg else step_note
    return ExecutionOutcome(
        ok,
        msg or "",
        extracted_data=extracted_data,
        step_log=(data or {}).get("step_log"),
        execution_warnings=(data or {}).get("execution_warnings"),
    )


async def _run_with_self_heal(
    macro: Macro,
    *,
    thread_id: str,
    script: MacroScript,
    params: dict[str, Any] | None,
    project_id: int,
) -> ExecutionOutcome:
    """MacroService run with the unified self-healing fallback (web policy)."""
    from app.core.engine.agent import run_agent_background
    from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
    from app.core.learning.macro.service import MacroService
    from app.utils.template import render_template

    exec_params = dict(params or {})
    exec_params["macro_id"] = macro.id
    exec_params["macro_name"] = macro.name

    result = await MacroService.run(
        thread_id=thread_id, script_input=script, params=exec_params, macro=macro
    )

    result_step_log = (
        (result or {}).get("step_log")
        if isinstance(result, dict)
        else getattr(result, "step_log", None)
    )
    result_warnings = (
        (result or {}).get("execution_warnings")
        if isinstance(result, dict)
        else getattr(result, "execution_warnings", None)
    )

    if result.get("status") != RUN_RESULT_FALLBACK_REQUIRED:
        return ExecutionOutcome(
            bool(result.get("success")),
            result.get("message") or "",
            extracted_data=result.get("extracted_data") or {},
            step_log=result_step_log,
            execution_warnings=result_warnings,
        )

    if not result.get("allow_self_healing", True):
        logger.warning(
            "[%s] Macro failed, self-healing disabled (reason: %s)",
            thread_id,
            result.get("healing_disabled_reason", "unknown"),
        )
        return ExecutionOutcome(
            False, result.get("message") or "", step_log=result_step_log
        )

    logger.warning("[%s] Macro failed, triggering agentic fallback", thread_id)
    failure_context = dict(result.get("fallback_context") or {})
    if result.get("message"):
        failure_context.setdefault("error_message", result["message"])
    fallback_msg = render_template(
        "core/learning/self_healing.prompt.j2",
        skill_name=macro.name,
        failure_context=failure_context,
    )
    dispatched = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=fallback_msg,
        project_id=project_id,
        model=None,
        metadata={"goal_prefix": "[Self-Healing] "},
    )
    if dispatched.status == DispatchStatus.FAILED:
        logger.error("[MacroFallback] Dispatch failed: %s", dispatched.error)
        return ExecutionOutcome(
            False,
            f"Self-healing dispatch failed: {dispatched.error}",
            step_log=result_step_log,
        )

    # 后台派发 Agent 恢复：立即返回 fell_back=True，不阻塞 web/chat 的 HTTP 响应
    # （原实现 await run_agent_background，会把宏失败的自愈拖到几分钟级，导致请求挂死）。
    asyncio.create_task(run_agent_background(thread_id, dispatched.inputs))
    return ExecutionOutcome(
        False, result.get("message") or "", fell_back=True, step_log=result_step_log
    )
