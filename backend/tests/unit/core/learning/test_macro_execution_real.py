"""Real MacroEngine / MacroService execution with OS-free steps.

dump steps write to a file, so `{{ param }}` injection becomes observable
without touching the desktop/browser drivers. Only the agent-dispatch boundary
of the self-healing fallback is stubbed.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.schemas import MacroScript
from app.core.execution.macro.service import MacroService


@pytest.fixture(autouse=True)
def _no_monitor(monkeypatch):
    """Monitoring is infrastructure (writes via the mocked session factory in
    unit mode); stub it like the event bus."""
    from app.core.monitoring.activity import activity_monitor

    monkeypatch.setattr(activity_monitor, "start_run", AsyncMock())
    monkeypatch.setattr(activity_monitor, "end_run", AsyncMock())
    monkeypatch.setattr(activity_monitor, "log_event", AsyncMock())


@pytest.mark.asyncio
async def test_macro_engine_empty_steps_succeeds_real():
    script = MacroScript.from_yaml("steps: []")
    ok, _msg, data = await MacroEngine.execute("t-real", script, params={})
    assert ok is True
    assert data is None


@pytest.mark.asyncio
async def test_macro_engine_param_injection_observable_real(tmp_path):
    template = tmp_path / "out-{{ slot }}.json"
    script = MacroScript(
        steps=[
            {
                "step_number": 1,
                "type": "dump",
                "source": "desktop",
                "payload": {"path": str(template)},
            }
        ]
    )

    ok, _msg, _data = await MacroEngine.execute(
        "t-real", script, params={"slot": "VALUE"}
    )

    assert ok is True
    assert (tmp_path / "out-VALUE.json").exists()
    assert not template.exists()


@pytest.mark.asyncio
async def test_macro_service_run_dump_step_real(tmp_path):
    out = tmp_path / "dump.json"
    result = await MacroService.run(
        thread_id="t-real",
        script_input=[
            {"step_number": 1, "type": "dump", "payload": {"path": str(out)}}
        ],
        params={},
    )

    assert result.success is True
    assert result.status != "fallback_required"
    assert json.loads(out.read_text()) == {}


@pytest.mark.asyncio
async def test_run_deterministic_empty_script_no_dispatch(monkeypatch):
    from app.core.execution.macro.runner import WEB_POLICY, run_deterministic

    dispatch = AsyncMock()
    monkeypatch.setattr("app.core.engine.dispatch.dispatch_agent_run", dispatch)
    macro = MagicMock(id=1, name="s", allow_self_healing=True)
    macro.is_routable.return_value = True

    outcome = await run_deterministic(
        macro,
        thread_id="t",
        params={},
        project_id=1,
        script=MacroScript(steps=[]),
        policy=WEB_POLICY,
    )

    assert outcome.ok is False
    assert outcome.fell_back is False
    dispatch.assert_not_called()
