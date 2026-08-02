"""SkillExecutionService against real DB rows and the real MacroEngine.

Pins the unified gates (preflight) and the one intentional policy divergence:
WEB_POLICY self-heals on macro failure, VOICE_POLICY fails fast and never
touches the healing machinery.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.execution.macro.runner import (
    VOICE_POLICY,
    WEB_POLICY,
    MacroGateError,
    preflight,
    run_deterministic,
)
from app.core.execution.macro.schemas import MacroScript
from app.infrastructure.database import session_scope
from app.models.macro import Macro

_DUMP_YAML = """steps:
  - step_number: 1
    type: dump
    payload:
      path: /tmp/skill_exec_test_dump.json
"""

_MOBILE_YAML = """steps:
  - step_number: 1
    type: action
    source: mobile
    payload:
      action: tap
"""


async def _insert_macro(**kwargs) -> Macro:
    async with session_scope() as db:
        macro = Macro(
            name=kwargs.pop("name", "s"),
            description="",
            trigger_patterns=[],
            parameters=kwargs.pop("parameters", []),
            macro_script=kwargs.pop("macro_script", _DUMP_YAML),
            status=kwargs.pop("status", "pending_review"),
            is_active=kwargs.pop("is_active", False),
            member_id=kwargs.pop("member_id", 0),
            **kwargs,
        )
        db.add(macro)
        await db.flush()
        await db.refresh(macro)
        return macro


# ------------------------------------------------------------------ preflight


@pytest.mark.asyncio
async def test_preflight_rejects_not_routable(_real_db):
    macro = await _insert_macro(status="pending_review", is_active=False)

    with pytest.raises(MacroGateError) as exc:
        preflight(macro, {})

    assert exc.value.code == "not_routable"
    assert exc.value.message == (
        "Macro is not active (status: pending_review); confirm it before executing"
    )


@pytest.mark.asyncio
async def test_preflight_rejects_missing_params(_real_db):
    macro = await _insert_macro(
        status="verified",
        is_active=True,
        parameters=[{"name": "city", "type": "string", "required": True}],
    )

    with pytest.raises(MacroGateError) as exc:
        preflight(macro, {})

    assert exc.value.code == "missing_params"
    assert exc.value.message == "Missing required parameters: city"


@pytest.mark.asyncio
async def test_preflight_rejects_bad_macro(_real_db):
    macro = await _insert_macro(
        status="verified",
        is_active=True,
        macro_script="- [invalid",
    )

    with pytest.raises(MacroGateError) as exc:
        preflight(macro, {})

    assert exc.value.code == "bad_macro"
    assert exc.value.message.startswith("Failed to parse macro YAML")


@pytest.mark.asyncio
async def test_preflight_parses_deterministic_macro(_real_db):
    macro = await _insert_macro(
        status="verified",
        is_active=True,
        macro_script=_DUMP_YAML,
    )

    script = preflight(macro, {})

    assert isinstance(script, MacroScript)
    assert len(script.steps) == 1


# ---------------------------------------------------------- run_deterministic


@pytest.mark.asyncio
async def test_voice_policy_executes_desktop_macro(_real_db, tmp_path):
    out = tmp_path / "dump.json"
    script = MacroScript(
        steps=[
            {
                "step_number": 1,
                "type": "dump",
                "source": "desktop",
                "payload": {"path": str(out)},
            }
        ]
    )
    macro = SimpleNamespace(id=1, name="s")

    outcome = await run_deterministic(
        macro, thread_id="t", params={}, project_id=1, script=script, policy=VOICE_POLICY
    )

    assert outcome.ok is True
    assert out.exists()


@pytest.mark.asyncio
async def test_voice_policy_rejects_mobile_source(_real_db):
    script = MacroScript.from_yaml(_MOBILE_YAML)
    macro = SimpleNamespace(id=1, name="s")

    outcome = await run_deterministic(
        macro, thread_id="t", params={}, project_id=1, script=script, policy=VOICE_POLICY
    )

    assert outcome.ok is False
    assert "unsupported macro source for voice" in outcome.message


@pytest.mark.asyncio
async def test_voice_policy_never_self_heals(_real_db, monkeypatch):
    """The one intentional divergence: on macro failure the voice policy must
    fail fast without touching MacroService/healing dispatch."""
    monkeypatch.setattr(
        "app.core.execution.macro.engine.MacroEngine.execute",
        AsyncMock(return_value=(False, "step 3 failed", None)),
    )
    service_run = AsyncMock()
    monkeypatch.setattr(
        "app.core.execution.macro.service.MacroService.run", service_run
    )
    dispatch = AsyncMock()
    monkeypatch.setattr("app.core.engine.dispatch.dispatch_agent_run", dispatch)

    outcome = await run_deterministic(
        SimpleNamespace(id=1, name="s"),
        thread_id="t",
        params={},
        project_id=1,
        script=MacroScript(
            steps=[{"step_number": 1, "type": "dump", "source": "desktop", "payload": {}}]
        ),
        policy=VOICE_POLICY,
    )

    assert outcome.ok is False
    assert outcome.message == "step 3 failed"
    assert outcome.fell_back is False
    service_run.assert_not_called()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_web_policy_success(_real_db, monkeypatch):
    service_run = AsyncMock(return_value={"success": True, "message": "done"})
    monkeypatch.setattr(
        "app.core.execution.macro.service.MacroService.run",
        service_run,
    )

    outcome = await run_deterministic(
        SimpleNamespace(id=1, name="s"),
        thread_id="t",
        params={"q": "x"},
        project_id=1,
        script=MacroScript(steps=[{"step_number": 1, "type": "dump", "payload": {}}]),
        policy=WEB_POLICY,
    )

    assert outcome.ok is True
    assert outcome.message == ""
    service_run.assert_not_called()


@pytest.mark.asyncio
async def test_web_policy_self_heal_dispatches_agent(_real_db, monkeypatch):
    monkeypatch.setattr(
        "app.core.execution.macro.engine.MacroEngine.execute",
        AsyncMock(return_value=(False, "fast path failed", None)),
    )
    monkeypatch.setattr(
        "app.core.execution.macro.service.MacroService.run",
        AsyncMock(
            return_value={
                "status": "fallback_required",
                "allow_self_healing": True,
                "message": "macro broke",
                "fallback_context": {"step": 3},
            }
        ),
    )
    dispatch = AsyncMock(return_value=SimpleNamespace(status="started", inputs={"i": 1}))
    monkeypatch.setattr("app.core.engine.dispatch.dispatch_agent_run", dispatch)
    bg = AsyncMock()
    monkeypatch.setattr("app.core.engine.background_agent.run_agent_background", bg)

    outcome = await run_deterministic(
        SimpleNamespace(id=7, name="weather"),
        thread_id="t",
        params={},
        project_id=3,
        script=MacroScript(steps=[{"step_number": 1, "type": "dump", "payload": {}}]),
        policy=WEB_POLICY,
    )

    assert outcome.fell_back is True
    assert outcome.ok is False
    assert dispatch.call_args.kwargs["project_id"] == 3
    assert dispatch.call_args.kwargs["metadata"] == {"goal_prefix": "[Self-Healing] "}
    bg.assert_awaited_once_with("t", {"i": 1})


@pytest.mark.asyncio
async def test_web_policy_healing_disabled_by_policy(_real_db, monkeypatch):
    monkeypatch.setattr(
        "app.core.execution.macro.engine.MacroEngine.execute",
        AsyncMock(return_value=(False, "fast path failed", None)),
    )
    monkeypatch.setattr(
        "app.core.execution.macro.service.MacroService.run",
        AsyncMock(
            return_value={
                "status": "fallback_required",
                "allow_self_healing": False,
                "message": "macro broke",
                "healing_disabled_reason": "user disabled",
            }
        ),
    )
    dispatch = AsyncMock()
    monkeypatch.setattr("app.core.engine.dispatch.dispatch_agent_run", dispatch)

    outcome = await run_deterministic(
        SimpleNamespace(id=1, name="s"),
        thread_id="t",
        params={},
        project_id=1,
        script=MacroScript(steps=[{"step_number": 1, "type": "dump", "payload": {}}]),
        policy=WEB_POLICY,
    )

    assert outcome.ok is False
    assert outcome.fell_back is False
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_web_policy_dispatch_failure_surfaces(_real_db, monkeypatch):
    monkeypatch.setattr(
        "app.core.execution.macro.engine.MacroEngine.execute",
        AsyncMock(return_value=(False, "fast path failed", None)),
    )
    monkeypatch.setattr(
        "app.core.execution.macro.service.MacroService.run",
        AsyncMock(
            return_value={
                "status": "fallback_required",
                "allow_self_healing": True,
                "message": "macro broke",
                "fallback_context": {},
            }
        ),
    )
    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run",
        AsyncMock(return_value=SimpleNamespace(status="failed", error="no model")),
    )

    outcome = await run_deterministic(
        SimpleNamespace(id=1, name="s"),
        thread_id="t",
        params={},
        project_id=1,
        script=MacroScript(steps=[{"step_number": 1, "type": "dump", "payload": {}}]),
        policy=WEB_POLICY,
    )

    assert outcome.ok is False
    assert "dispatch failed" in outcome.message
