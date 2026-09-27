"""Tests for the unified MacroEngine lifecycle API (validate → run → stop).

Covers the semantic contract exposed through the facade:
- ``validate`` gate: returns a script or raises MacroGateError
- ``run`` result statuses: not_routable / missing_params / bad_macro /
  cancelled / fallback_required
- ``stop`` signals the run for cancellation
"""

import pytest

from app.core.learning.macro import MacroEngine, MacroGateError, MacroScript
from app.models.macro import Macro

VALID_SCRIPT = """steps:
  - type: action
    event_type: click
    payload:
      selector: "#btn"
"""


@pytest.fixture(autouse=True)
def _clear_script_cache():
    """Test macros share id=None, so the runner's script cache (keyed by id)
    would leak a parsed script across tests. Clear it around each test."""
    yield


def _macro(status: str = "verified", is_active: bool = True, parameters=None, script=VALID_SCRIPT):
    return Macro(
        name="test-macro",
        description="",
        trigger_patterns=[],
        parameters=parameters or [],
        macro_script=script,
        status=status,
        is_active=is_active,
    )


class TestValidate:
    @pytest.mark.asyncio
    async def test_validate_returns_script(self):
        script = await MacroEngine.validate(_macro(), {})
        assert isinstance(script, MacroScript)
        assert len(script.steps) >= 1

    @pytest.mark.asyncio
    async def test_validate_rejects_missing_params(self):
        macro = _macro(parameters=[{"name": "req", "required": True}])
        with pytest.raises(MacroGateError):
            await MacroEngine.validate(macro, {})


class TestRunGateStatuses:
    @pytest.mark.asyncio
    async def test_run_not_routable(self):
        macro = _macro(status="pending_review", is_active=False)
        result = await MacroEngine.run("t", macro, params={})
        assert result.success is False
        assert result.status == "not_routable"

    @pytest.mark.asyncio
    async def test_run_missing_params(self):
        macro = _macro(parameters=[{"name": "req", "required": True}])
        result = await MacroEngine.run("t", macro, params={})
        assert result.success is False
        assert result.status == "missing_params"

    @pytest.mark.asyncio
    async def test_run_bad_macro_script(self):
        macro = _macro(script="not: [valid: yaml: [")
        result = await MacroEngine.run("t", macro, params={})
        assert result.success is False
        assert result.status == "bad_macro"


class TestRunLifecycleStatuses:
    @pytest.mark.asyncio
    async def test_run_cancelled(self, monkeypatch):
        from app.core.exceptions import AgentCancelledException
        from app.core.learning.macro.engine import activity_monitor

        async def fake_check_cancellation(*args, **kwargs):  # noqa: ARG001
            raise AgentCancelledException("cancelled by user")

        monkeypatch.setattr(
            activity_monitor, "check_cancellation", fake_check_cancellation
        )
        result = await MacroEngine.run("t", _macro(), params={})
        assert result.success is False
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_run_fallback_required(self, monkeypatch):
        from app.core.learning.macro import runner

        async def fake_run_deterministic(*args, **kwargs):  # noqa: ARG001
            return runner.ExecutionOutcome(False, "step failed", fell_back=True)

        monkeypatch.setattr(runner, "run_deterministic", fake_run_deterministic)
        result = await MacroEngine.run("t", _macro(), params={})
        assert result.success is False
        assert result.status == "fallback_required"

    @pytest.mark.asyncio
    async def test_run_success(self, monkeypatch):
        from app.core.learning.macro import runner

        async def fake_run_deterministic(*args, **kwargs):  # noqa: ARG001
            return runner.ExecutionOutcome(True, "done")

        monkeypatch.setattr(runner, "run_deterministic", fake_run_deterministic)
        result = await MacroEngine.run("t", _macro(), params={})
        assert result.success is True
        assert result.status is None


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_signals_run(self, monkeypatch):
        from app.core.learning.macro.engine import activity_monitor

        stopped: list[str] = []

        async def fake_stop_run(thread_id: str):
            stopped.append(thread_id)

        monkeypatch.setattr(activity_monitor, "stop_run", fake_stop_run)
        await MacroEngine.stop("thread-42")
        assert stopped == ["thread-42"]
