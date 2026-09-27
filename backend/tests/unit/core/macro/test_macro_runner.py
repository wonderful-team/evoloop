"""Coverage for runner.py: preflight gates, navigation detection and policy
scanning helpers."""

from unittest.mock import AsyncMock

import pytest

from app.core.learning.constants import ExecutionPolicy
from app.core.learning.macro.runner import (
    MacroGateError,
    _collect_sources,
    _scan_steps_risk,
    _step_requires_ui,
    get_navigation_info,
    is_navigation_macro,
    preflight,
)
from app.core.learning.macro.schemas import (
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)
from app.models.macro import Macro

NAV_SCRIPT = """steps:
  - type: action
    event_type: frontend_navigate
    payload:
      route: "/shop/goods/list"
      feedback: "已打开商品列表"
"""

CLICK_SCRIPT = """steps:
  - type: action
    event_type: click
    payload:
      selector: "#btn"
"""


def _macro(script=CLICK_SCRIPT, status="verified", is_active=True, parameters=None) -> Macro:
    return Macro(
        name="m",
        description="",
        trigger_patterns=[],
        parameters=parameters or [],
        macro_script=script,
        status=status,
        is_active=is_active,
    )


class TestNavigationDetection:
    def test_get_navigation_info(self):
        info = get_navigation_info(_macro(script=NAV_SCRIPT))
        assert info is not None
        route, feedback = info
        assert route == "/shop/goods/list"
        assert feedback == "已打开商品列表"

    def test_non_navigation_returns_none(self):
        assert get_navigation_info(_macro(script=CLICK_SCRIPT)) is None

    def test_non_string_script_returns_none(self):
        macro = _macro()
        macro.macro_script = None
        assert get_navigation_info(macro) is None

    def test_is_navigation_macro(self):
        assert is_navigation_macro(_macro(script=NAV_SCRIPT)) == "/shop/goods/list"
        assert is_navigation_macro(_macro(script=CLICK_SCRIPT)) is None


class TestPolicyHelpers:
    def test_collect_sources(self):
        steps = [
            MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM, steps=[]),
            MacroStep(type=MacroStepType.ACTION, source=MacroSource.DESKTOP, steps=[]),
        ]
        sources = _collect_sources(steps)
        assert "dom" in sources and "desktop" in sources

    def test_step_requires_ui(self):
        click = MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)
        assert _step_requires_ui(click) is True
        wait = MacroStep(type=MacroStepType.ACTION, event_type="wait", source=MacroSource.DOM)
        assert _step_requires_ui(wait) is False
        native = MacroStep(type=MacroStepType.NATIVE, source=MacroSource.DOM)
        assert _step_requires_ui(native) is False

    def test_scan_steps_risk_disallowed_family(self):
        policy = ExecutionPolicy(
            allow_self_heal=False, allowed_families=frozenset({"act"})
        )
        step = MacroStep(type=MacroStepType.ACTION, event_type="run_js", source=MacroSource.DOM)
        reason = _scan_steps_risk([step], policy)
        assert reason is not None and "family" in reason

    def test_scan_steps_risk_allowed(self):
        policy = ExecutionPolicy(
            allow_self_heal=False, allowed_families=frozenset({"act"})
        )
        step = MacroStep(type=MacroStepType.ACTION, event_type="click", source=MacroSource.DOM)
        assert _scan_steps_risk([step], policy) is None


class TestPreflight:
    def test_not_routable(self):
        with pytest.raises(MacroGateError) as ei:
            preflight(_macro(status="pending_review", is_active=False), {})
        assert ei.value.code == "not_routable"

    def test_missing_params(self):
        macro = _macro(parameters=[{"name": "req", "required": True}])
        with pytest.raises(MacroGateError) as ei:
            preflight(macro, {})
        assert ei.value.code == "missing_params"

    def test_bad_macro_script(self):
        with pytest.raises(MacroGateError) as ei:
            preflight(_macro(script="not: [valid: yaml: ["), {})
        assert ei.value.code == "bad_macro"

    def test_valid_returns_script(self):
        script = preflight(_macro(), {})
        assert isinstance(script, MacroScript)
        assert len(script.steps) >= 1


@pytest.mark.asyncio
class TestRunDeterministicGates:
    async def test_unsupported_source_rejected(self):
        from app.core.learning.macro.runner import run_deterministic

        policy = ExecutionPolicy(
            allow_self_heal=False, allowed_sources=frozenset({"desktop"})
        )
        script = preflight(_macro(), {})
        outcome = await run_deterministic(
            _macro(),
            thread_id="t",
            params={},
            project_id=0,
            script=script,
            policy=policy,
        )
        assert outcome.ok is False
        assert "unsupported macro source" in outcome.message


class TestVaultFill:
    @pytest.mark.asyncio
    async def test_fills_missing_from_vault(self, monkeypatch):
        import app.core.learning.macro.runner as runner

        monkeypatch.setattr(
            runner.SecureVaultService,
            "list_credentials",
            classmethod(lambda cls, **kw: [{"identifier": "c1", "project_id": None}]),
        )
        monkeypatch.setattr(
            runner.SecureVaultService,
            "get_credential_payload",
            classmethod(lambda cls, identifier, project_id=None: {"username": "u", "password": "p"}),
        )
        macro = _macro(parameters=[{"name": "username", "required": True}])
        params = {}
        filled = runner.vault_fill_params(macro, ["username", "password"], params)
        assert filled >= 1
        assert params.get("username") == "u"

    def test_no_credentials(self, monkeypatch):
        import app.core.learning.macro.runner as runner

        monkeypatch.setattr(
            runner.SecureVaultService,
            "list_credentials",
            classmethod(lambda cls, **kw: []),
        )
        macro = _macro()
        params = {}
        assert runner.vault_fill_params(macro, ["x"], params) == 0


class TestResolveProjectUrl:
    @pytest.mark.asyncio
    async def test_resolves_url(self, monkeypatch):
        import app.core.learning.macro.runner as runner

        monkeypatch.setattr(
            runner, "get_project_path", AsyncMock(return_value="/proj")
        )
        monkeypatch.setattr(runner, "read_project_json", lambda p: {"url": "https://x.com"})
        assert await runner.resolve_project_base_url(1) == "https://x.com"

    @pytest.mark.asyncio
    async def test_no_project_returns_none(self):
        import app.core.learning.macro.runner as runner

        assert await runner.resolve_project_base_url(None) is None


@pytest.mark.asyncio
class TestSelfHealPath:
    async def test_run_with_self_heal_dispatches(self, monkeypatch):

        import app.core.learning.macro.runner as runner

        monkeypatch.setattr(
            "app.core.engine.dispatch.dispatch_agent_run",
            AsyncMock(return_value=type("D", (), {"status": "dispatched", "inputs": {}})()),
        )
        monkeypatch.setattr(
            "app.core.engine.agent.run_agent_background", AsyncMock()
        )
        monkeypatch.setattr(
            "app.utils.template.render_template", lambda *a, **k: "prompt"
        )
        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.run",
            AsyncMock(return_value={"status": "fallback_required", "allow_self_healing": True, "message": "fail", "fallback_context": {}}),
        )
        macro = _macro()
        outcome = await runner._run_with_self_heal(
            macro,
            thread_id="t",
            script=MacroScript(steps=[]),
            params={},
            project_id=1,
        )
        assert outcome.fell_back is True

    async def test_run_with_self_heal_policy_disabled(self, monkeypatch):
        import app.core.learning.macro.runner as runner

        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.run",
            AsyncMock(return_value={"status": "fallback_required", "allow_self_healing": False, "message": "no"}),
        )
        macro = _macro()
        outcome = await runner._run_with_self_heal(
            macro,
            thread_id="t",
            script=MacroScript(steps=[]),
            params={},
            project_id=1,
        )
        assert outcome.ok is False
        assert outcome.fell_back is False
