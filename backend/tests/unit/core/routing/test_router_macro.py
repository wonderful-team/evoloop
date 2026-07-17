"""Unit tests for the router's execute_macro branch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.routing.router import ROUTE_TOOLS, _from_tool_call
from app.core.routing.schemas import RouteRequest


def _req(text: str = "查商品价格") -> RouteRequest:
    return RouteRequest(text=text, thread_id="t1")


class TestExecuteMacroTool:
    def test_tool_registered(self):
        names = [t["function"]["name"] for t in ROUTE_TOOLS]
        assert names == ["execute_skill", "execute_macro", "local_action", "delegate"]

    def test_valid_macro_id_routes(self):
        decision = _from_tool_call(
            "execute_macro",
            {"macro_id": 42, "params": {"query": "铰链"}},
            ids={"macro:42", "skill:7"},
            req=_req(),
            raw=None,
        )
        assert decision.target_type == "macro"
        assert decision.target == {"type": "macro", "id": 42}
        assert decision.params == {"query": "铰链"}
        assert decision.status == "routed"

    def test_hallucinated_macro_id_delegates(self):
        decision = _from_tool_call(
            "execute_macro",
            {"macro_id": 999},
            ids={"macro:42"},
            req=_req(),
            raw=None,
        )
        assert decision.target_type == "agent"
        assert decision.params["task"] == "查商品价格"

    def test_missing_macro_id_delegates(self):
        decision = _from_tool_call(
            "execute_macro",
            {},
            ids={"macro:42"},
            req=_req(),
            raw=None,
        )
        assert decision.target_type == "agent"


class TestRunMacroGates:
    async def test_money_macro_requires_confirmation(self, monkeypatch):
        from app.core.routing import executor
        from app.core.routing.schemas import RouteDecision

        macro = SimpleNamespace(
            id=5,
            name="改{query}goods价格",
            risk_tier="money",
            requires_confirmation=True,
            parameters=[],
            macro_script="steps:\n- step_number: 1\n  type: action\n  event_type: click\n  source: dom\n  payload: {}\n",
            is_routable=lambda: True,
        )
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(return_value=macro),
        )
        # §16.5: money tier is not hard-blocked — it delegates to the Agent
        # for multi-turn voice HITL confirmation.
        delegated = []
        monkeypatch.setattr(
            executor,
            "_run_agent",
            AsyncMock(side_effect=lambda *a, **kw: delegated.append(kw)),
        )

        decision = RouteDecision(
            target_type="macro", target={"id": 5}, params={}, reason="t"
        )
        await executor._run_macro("t-money", decision)

        assert delegated and delegated[0]["metadata"]["requires_hitl"] is True
        assert delegated[0]["metadata"]["macro_id"] == 5

    async def test_dom_macro_passes_voice_source_gate(self, monkeypatch):
        from app.core.routing import executor
        from app.core.routing.schemas import RouteDecision

        macro = SimpleNamespace(
            id=6,
            name="查看{query}goods",
            risk_tier="ui",
            requires_confirmation=False,
            parameters=[],
            macro_script="steps:\n- step_number: 1\n  type: action\n  event_type: navigate\n  source: dom\n  payload: {url: /x}\n",
            is_routable=lambda: True,
        )
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(return_value=macro),
        )
        pushed = []
        monkeypatch.setattr(
            executor,
            "push_voice_result",
            AsyncMock(side_effect=lambda t, s, m: pushed.append((s, m))),
        )
        engine_exec = AsyncMock(return_value=(True, "ok", {}))
        monkeypatch.setattr(
            "app.core.execution.macro.engine.MacroEngine.execute", engine_exec
        )

        decision = RouteDecision(
            target_type="macro", target={"id": 6}, params={}, reason="t"
        )
        await executor._run_macro("t-dom", decision)

        assert pushed and pushed[-1][0] == "done", pushed
        engine_exec.assert_awaited_once()

    async def test_execution_failure_relays_to_agent(self, monkeypatch):
        """宏执行失败 → Agent 接力（带失败简报），不直接推 failed。"""
        from app.core.routing import executor
        from app.core.routing.schemas import RouteDecision

        macro = SimpleNamespace(
            id=7,
            name="查看{query}goods",
            risk_tier="ui",
            requires_confirmation=False,
            parameters=[],
            macro_script="steps:\n- step_number: 1\n  type: action\n  event_type: click\n  source: dom\n  payload: {}\n",
            is_routable=lambda: True,
        )
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(return_value=macro),
        )
        pushed = []
        monkeypatch.setattr(
            executor,
            "push_voice_result",
            AsyncMock(side_effect=lambda t, s, m: pushed.append((s, m))),
        )
        monkeypatch.setattr(
            "app.core.execution.macro.engine.MacroEngine.execute",
            AsyncMock(
                return_value=(
                    False,
                    "selector 超时",
                    {
                        "step_number": 3,
                        "event_type": "click",
                        "screenshot_path": "/tmp/x.png",
                    },
                )
            ),
        )
        delegated = []
        monkeypatch.setattr(
            executor,
            "_run_agent",
            AsyncMock(side_effect=lambda *a, **kw: delegated.append(kw)),
        )

        decision = RouteDecision(
            target_type="macro",
            target={"id": 7},
            params={"task": "查铰链"},
            reason="t",
        )
        await executor._run_macro("t-relay", decision)

        assert not pushed, f"不应直接推 failed: {pushed}"
        assert delegated, "执行失败未接力 Agent"
        brief = delegated[0]["message_content"]
        assert "查铰链" in brief
        assert "查看{query}goods" in brief
        assert "第 3 步" in brief
        assert "selector 超时" in brief
        assert delegated[0]["metadata"]["macro_relay"] == "execution_failure"
        assert delegated[0]["metadata"]["failed_step"] == 3

    async def test_relay_respects_self_healing_policy(self, monkeypatch):
        """自愈开关禁用时，执行失败推 failed，不接力 Agent。"""
        from app.core.routing import executor
        from app.core.routing.schemas import RouteDecision

        macro = SimpleNamespace(
            id=8,
            name="查看{query}goods",
            risk_tier="ui",
            requires_confirmation=False,
            parameters=[],
            macro_script="steps:\n- step_number: 1\n  type: action\n  event_type: click\n  source: dom\n  payload: {}\n",
            is_routable=lambda: True,
        )
        monkeypatch.setattr(
            "app.core.execution.macro.lifecycle.load_macro",
            AsyncMock(return_value=macro),
        )
        pushed = []
        monkeypatch.setattr(
            executor,
            "push_voice_result",
            AsyncMock(side_effect=lambda t, s, m: pushed.append((s, m))),
        )
        monkeypatch.setattr(
            "app.core.execution.macro.engine.MacroEngine.execute",
            AsyncMock(return_value=(False, "selector 超时", {"step_number": 3})),
        )
        delegated = []
        monkeypatch.setattr(
            executor,
            "_run_agent",
            AsyncMock(side_effect=lambda *a, **kw: delegated.append(kw)),
        )
        monkeypatch.setattr(
            "app.core.execution.macro.healing_policy.SelfHealingPolicy.check",
            lambda **kw: SimpleNamespace(
                allowed=False, reason="全局禁用", source="global"
            ),
        )

        decision = RouteDecision(
            target_type="macro", target={"id": 8}, params={}, reason="t"
        )
        await executor._run_macro("t-no-heal", decision)

        assert not delegated, "自愈禁用时不应接力 Agent"
        assert pushed and pushed[-1][0] == "failed"
        assert "自愈已禁用" in pushed[-1][1]
