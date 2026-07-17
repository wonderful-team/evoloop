"""Multi-intent orchestration: decompose -> route_many -> execute_many."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.routing import executor
from app.core.routing.decompose import Intent, _parse_intents, decompose
from app.core.routing.schemas import RouteDecision


class TestParseIntents:
    def test_valid_chain(self):
        raw = '{"intents": [{"text": "查铰链价格"}, {"text": "铰链降价10%", "depends_on": 1, "param_exprs": {"new_value": "{{1.value}} * 0.9"}}]}'
        intents = _parse_intents(raw)
        assert intents and len(intents) == 2
        assert intents[1].depends_on == 1
        assert intents[1].param_exprs == {"new_value": "{{1.value}} * 0.9"}

    def test_single_intent_rejected(self):
        assert _parse_intents('{"intents": [{"text": "查价格"}]}') is None

    def test_forward_reference_rejected(self):
        raw = '{"intents": [{"text": "a", "depends_on": 2}, {"text": "b"}]}'
        assert _parse_intents(raw) is None

    def test_ref_to_later_intent_rejected(self):
        raw = '{"intents": [{"text": "a", "param_exprs": {"x": "{{2.v}} * 2"}}, {"text": "b"}]}'
        assert _parse_intents(raw) is None

    def test_garbage_rejected(self):
        assert _parse_intents("not json at all") is None
        assert _parse_intents('{"intents": "many"}') is None

    def test_wrapped_json_accepted(self):
        raw = '好的，拆分如下：\n{"intents": [{"text": "a"}, {"text": "b"}]}\n完毕'
        assert _parse_intents(raw) is not None


class TestDecompose:
    async def test_no_connector_skips_llm(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "app.core.routing.router._create_route_llm",
            AsyncMock(side_effect=lambda: called.append(1)),
        )
        assert await decompose("查一下铰链的价格") is None
        assert not called

    async def test_connector_uses_llm(self, monkeypatch):
        llm = SimpleNamespace(
            ainvoke=AsyncMock(
                return_value=SimpleNamespace(
                    content='{"intents": [{"text": "查铰链价格"}, {"text": "铰链降价10%", "depends_on": 1, "param_exprs": {"new_value": "{{1.value}} * 0.9"}}]}'
                )
            )
        )
        monkeypatch.setattr(
            "app.core.routing.router._create_route_llm", AsyncMock(return_value=llm)
        )
        intents = await decompose("查铰链价格，然后降价10%")
        assert intents and len(intents) == 2

    async def test_llm_failure_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.routing.router._create_route_llm",
            AsyncMock(side_effect=ConnectionError("lm studio down")),
        )
        assert await decompose("查价格，然后降价") is None


class TestRouteMany:
    async def test_single_passthrough(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.routing.decompose.decompose", AsyncMock(return_value=None)
        )
        solo = RouteDecision(target_type="agent", params={"task": "x"}, reason="t")
        monkeypatch.setattr(
            "app.core.routing.router.route", AsyncMock(return_value=solo)
        )
        from app.core.routing.router import route_many
        from app.core.routing.schemas import RouteRequest

        out = await route_many(RouteRequest(text="查价格", thread_id="t"), [])
        assert out == [solo]

    async def test_multi_attaches_dependency_params(self, monkeypatch):
        intents = [
            Intent(text="查铰链价格"),
            Intent(
                text="铰链降价10%",
                depends_on=1,
                param_exprs={"new_value": "{{1.value}} * 0.9"},
            ),
        ]
        monkeypatch.setattr(
            "app.core.routing.decompose.decompose", AsyncMock(return_value=intents)
        )
        monkeypatch.setattr(
            "app.core.routing.retriever.retrieve", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            "app.core.routing.router.route",
            AsyncMock(
                side_effect=lambda req, c: RouteDecision(
                    target_type="macro",
                    target={"id": 1},
                    params={"query": "铰链"},
                    reason="t",
                )
            ),
        )
        from app.core.routing.router import route_many
        from app.core.routing.schemas import RouteRequest

        out = await route_many(
            RouteRequest(text="查铰链价格然后降价10%", thread_id="t"), []
        )
        assert len(out) == 2
        assert out[0].params["_intent_text"] == "查铰链价格"
        assert out[1].params["_depends_on"] == 1
        assert out[1].params["_param_exprs"] == {"new_value": "{{1.value}} * 0.9"}


class TestExecuteMany:
    def _decision(self, params: dict) -> RouteDecision:
        return RouteDecision(
            target_type="macro", target={"id": 1}, params=params, reason="t"
        )

    async def test_chain_resolves_dependent_params(self, monkeypatch):
        calls: list[dict] = []

        async def fake_execute(_tid, decision):
            calls.append(dict(decision.params or {}))
            if len(calls) == 1:
                return {"value": 100.0}
            return {}

        monkeypatch.setattr(executor, "execute", AsyncMock(side_effect=fake_execute))

        d1 = self._decision({"query": "铰链", "_intent_text": "查铰链价格"})
        d2 = self._decision(
            {
                "query": "铰链",
                "_intent_text": "铰链降价10%",
                "_depends_on": 1,
                "_param_exprs": {"new_value": "{{1.value}} * 0.9"},
            }
        )
        await executor.execute_many("t-chain", [d1, d2])

        assert len(calls) == 2
        assert calls[0] == {"query": "铰链"}
        assert calls[1]["new_value"] == 90.0
        assert all(not k.startswith("_") for c in calls for k in c)

    async def test_resolve_failure_relays_and_continues(self, monkeypatch):
        calls: list[dict] = []

        async def fake_execute(_tid, decision):
            calls.append(dict(decision.params or {}))
            return {}

        monkeypatch.setattr(executor, "execute", AsyncMock(side_effect=fake_execute))
        delegated = []
        monkeypatch.setattr(
            executor,
            "_run_agent",
            AsyncMock(side_effect=lambda *a, **kw: delegated.append(kw)),
        )

        d1 = self._decision({"query": "铰链", "_intent_text": "查铰链价格"})
        d2 = self._decision(
            {
                "query": "铰链",
                "_intent_text": "铰链降价10%",
                "_depends_on": 1,
                "_param_exprs": {"new_value": "{{1.missing}} * 0.9"},
            }
        )
        d3 = self._decision({"query": "螺丝", "_intent_text": "查螺丝库存"})
        await executor.execute_many("t-fallback", [d1, d2, d3])

        # d2 relayed to agent (not executed), d3 still ran
        assert len(calls) == 2
        assert delegated and delegated[0]["metadata"]["macro_relay"] == "resolve_failed"
        brief = delegated[0]["message_content"]
        assert "铰链降价10%" in brief and "绝对值" in brief

    async def test_single_decision_passthrough(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            executor,
            "execute",
            AsyncMock(side_effect=lambda t, d: calls.append(d)),
        )
        await executor.execute_many("t-solo", [self._decision({"query": "x"})])
        assert len(calls) == 1
