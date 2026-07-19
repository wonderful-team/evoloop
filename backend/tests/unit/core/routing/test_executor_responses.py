"""Response-strategy diversity tests for the voice executor (设计评审 2026-07-16 晚).

Covers every terminal speech branch the client can see:
  local no-op / macro done (short|empty-fallback|long) / macro failed relay vs
  healing-disabled / clarify / not-found / unroutable / missing-params /
  bad-script / source-gate / skill branches / agent hand-off /
  multi-intent resolve fallback.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.routing import executor
from app.core.routing.schemas import RouteDecision
from app.models.learning import LearnedSkill
from app.models.macro import Macro
from app.core.execution.macro import runner as skill_execution

SCRIPT_CLICK = (
    "steps:\n- step_number: 1\n  type: action\n  event_type: click\n"
    "  source: dom\n  payload: {}\n"
)
SCRIPT_MOBILE = SCRIPT_CLICK.replace("source: dom", "source: mobile")
SCRIPT_BAD = "steps: [unclosed"


def _macro(**over) -> SimpleNamespace:
    base = dict(
        id=1,
        name="WeChat 微信>关于微信",
        risk_tier="ui",
        requires_confirmation=False,
        parameters=[],
        macro_script=SCRIPT_CLICK,
        is_routable=lambda: True,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _decision(**over) -> RouteDecision:
    base = dict(target_type="macro", target={"id": 1}, params={}, reason="t")
    base.update(over)
    return RouteDecision(**base)


@pytest.fixture
def pushed(monkeypatch):
    out: list[tuple[str, str]] = []
    monkeypatch.setattr(
        executor,
        "push_voice_result",
        AsyncMock(side_effect=lambda t, s, m: out.append((s, m))),
    )
    return out


@pytest.fixture
def load_macro(monkeypatch):
    def _install(macro):
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(return_value=macro),
        )

    return _install


@pytest.fixture
def engine(monkeypatch):
    mock = AsyncMock(return_value=(True, "ok", {}))
    monkeypatch.setattr("app.core.execution.macro.engine.MacroEngine.execute", mock)
    return mock


class TestLocalNoOp:
    async def test_local_target_pushes_nothing(self, pushed):
        d = _decision(target_type="local", target={"type": "local", "id": "mute"})
        assert await executor.execute("t-local", d) is None
        assert pushed == []


class TestMacroDoneSummaries:
    async def test_short_summary_pushed_verbatim(self, pushed, load_macro, engine):
        load_macro(_macro())
        engine.return_value = (True, "价格 12.5 元", {})
        await executor._run_macro("t", _decision())
        assert pushed == [("done", "价格 12.5 元")]

    async def test_empty_summary_falls_back_to_leaf_name(self, pushed, load_macro, engine):
        load_macro(_macro())
        engine.return_value = (True, "", {})
        await executor._run_macro("t", _decision())
        assert pushed == [("done", "已完成关于微信")]

    async def test_empty_summary_web_macro_uses_full_name(self, pushed, load_macro, engine):
        load_macro(_macro(name="查商品价格"))
        engine.return_value = (True, None, {})
        await executor._run_macro("t", _decision())
        assert pushed == [("done", "已完成查商品价格")]

    async def test_long_summary_pushed_untruncated(self, pushed, load_macro, engine):
        """Server pushes as-is; the >=100-char truncation lives client-side."""
        load_macro(_macro())
        engine.return_value = (True, "x" * 150, {})
        await executor._run_macro("t", _decision())
        assert pushed == [("done", "x" * 150)]


class TestMacroFailurePaths:
    async def test_not_found(self, pushed, load_macro):
        load_macro(None)
        await executor._run_macro("t", _decision())
        assert pushed == [("failed", "macro #1 not found")]

    async def test_unroutable(self, pushed, load_macro):
        m = _macro()
        m.is_routable = lambda: False
        load_macro(m)
        await executor._run_macro("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "未确认" in pushed[0][1]

    async def test_missing_query_param_asks_clarify(self, pushed, load_macro):
        load_macro(_macro(parameters=[{"name": "query", "required": True}]))
        await executor._run_macro("t-clarify", _decision(params={"_text": "查价格"}))
        assert pushed and pushed[0][0] == "clarify" and pushed[0][1]

    async def test_missing_nonquery_param_fails(self, pushed, load_macro):
        load_macro(_macro(parameters=[{"name": "value", "required": True}]))
        await executor._run_macro("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "缺少参数" in pushed[0][1]

    async def test_bad_script(self, pushed, load_macro):
        load_macro(_macro(macro_script=SCRIPT_BAD))
        await executor._run_macro("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "宏脚本解析失败" in pushed[0][1]

    async def test_unsupported_source_gate(self, pushed, load_macro):
        load_macro(_macro(macro_script=SCRIPT_MOBILE))
        await executor._run_macro("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "unsupported macro source" in pushed[0][1]

    async def test_failure_with_healing_disabled_pushes_failed(
        self, pushed, load_macro, engine, monkeypatch
    ):
        load_macro(_macro())
        engine.return_value = (False, "selector 超时", None)
        monkeypatch.setattr(
            "app.core.execution.macro.healing_policy.SelfHealingPolicy.check",
            classmethod(
                lambda cls, macro=None, execution_params=None: SimpleNamespace(
                    allowed=False, reason="全局关闭"
                )
            ),
        )
        await executor._run_macro("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "自愈已禁用" in pushed[0][1]

    async def test_failure_with_healing_allowed_relays_no_failed_push(
        self, pushed, load_macro, engine, monkeypatch
    ):
        load_macro(_macro())
        engine.return_value = (False, "selector 超时", {"step_number": 1})
        relay = AsyncMock()
        monkeypatch.setattr(executor, "_relay_macro_failure", relay)
        await executor._run_macro("t", _decision())
        relay.assert_awaited_once()
        assert pushed == []  # 终态由 Agent 完成事件推回


class _FakeSession:
    def __init__(self, skill=None, macro=None):
        self._skill = skill
        self._macro = macro

    async def get(self, model, _id):
        if model is LearnedSkill:
            return self._skill
        if model is Macro:
            return self._macro
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _install_skill_session(monkeypatch, skill, macro=None):
    monkeypatch.setattr(executor, "session_scope", lambda: _FakeSession(skill, macro))


class TestSkillBranches:
    def _skill(self, name="查快递"):
        return SimpleNamespace(id=9, name=name, description="d", macro_id=1)

    async def test_skill_not_found(self, pushed, monkeypatch):
        _install_skill_session(monkeypatch, None, None)
        await executor._run_skill("t", _decision(target_type="skill", target={"id": 9}))
        assert pushed == [("failed", "skill #9 not found")]

    async def test_skill_gate_error(self, pushed, monkeypatch):
        _install_skill_session(monkeypatch, self._skill(), _macro())

        def _raise(macro, params):
            raise skill_execution.MacroGateError("bad_params", "参数不合格")

        monkeypatch.setattr(skill_execution, "preflight", _raise)
        await executor._run_skill("t", _decision(target_type="skill", target={"id": 9}))
        assert pushed == [("failed", "参数不合格")]

    async def test_skill_deterministic_done_empty_message_fallback(self, pushed, monkeypatch):
        _install_skill_session(monkeypatch, self._skill(), _macro())
        monkeypatch.setattr(skill_execution, "preflight", lambda m, p: object())
        monkeypatch.setattr(
            skill_execution,
            "run_deterministic",
            AsyncMock(return_value=SimpleNamespace(ok=True, message="")),
        )
        await executor._run_skill("t", _decision(target_type="skill", target={"id": 9}))
        assert pushed == [("done", "已完成查快递")]

    async def test_skill_deterministic_failed(self, pushed, monkeypatch):
        _install_skill_session(monkeypatch, self._skill(), _macro())
        monkeypatch.setattr(skill_execution, "preflight", lambda m, p: object())
        monkeypatch.setattr(
            skill_execution,
            "run_deterministic",
            AsyncMock(return_value=SimpleNamespace(ok=False, message="步骤2失败")),
        )
        await executor._run_skill("t", _decision(target_type="skill", target={"id": 9}))
        assert pushed == [("failed", "步骤2失败")]


class TestAgentHandoff:
    async def test_agent_target_dispatches_no_push(self, pushed, monkeypatch):
        agent = AsyncMock()
        monkeypatch.setattr(executor, "_run_agent", agent)
        d = _decision(
            target_type="agent", target={"type": "agent"}, params={"task": "写个周报"}
        )
        await executor.execute("t", d)
        agent.assert_awaited_once()
        assert pushed == []

    async def test_unexpected_exception_pushes_failed(self, pushed, monkeypatch):
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(side_effect=RuntimeError("db down")),
        )
        await executor.execute("t", _decision())
        assert pushed and pushed[0][0] == "failed" and "db down" in pushed[0][1]


