import json
from pathlib import Path

import pytest

from app.core.routing import router
from app.core.routing.schemas import RouteCandidate, RouteRequest

_GOLDEN = Path(__file__).parent / "golden" / "route_cases.json"
_CASES = json.loads(_GOLDEN.read_text(encoding="utf-8"))


class _Msg:
    def __init__(self, tool_call):
        self.tool_calls = [tool_call] if tool_call else []
        self.content = ""


class _Runnable:
    def __init__(self, msg):
        self._msg = msg

    async def ainvoke(self, _prompt):
        return self._msg


class _FakeLLM:
    def __init__(self, msg):
        self._msg = msg

    def bind_tools(self, _tools, tool_choice=None):
        return _Runnable(self._msg)


def _patch(monkeypatch, case):
    async def _boom():
        raise AssertionError("LLM must not be called for early-delegate cases")

    async def _create():
        return _FakeLLM(_Msg(case["tool_call"]))

    monkeypatch.setattr(router, "_min_score", lambda: float(case["min_score"]))
    if case["tool_call"] is None:
        monkeypatch.setattr(router, "_create_route_llm", _boom)
    else:
        monkeypatch.setattr(router, "_create_route_llm", _create)


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
@pytest.mark.asyncio
async def test_route_golden(case, monkeypatch):
    _patch(monkeypatch, case)
    candidates = [RouteCandidate(**c) for c in case["candidates"]]
    decision = await router.route(RouteRequest(text=case["text"], thread_id="t"), candidates)

    exp = case["expected"]
    assert decision.status == exp["status"]
    assert decision.target_type == exp["target_type"]
    if "target_id" in exp:
        assert decision.target.get("id") == exp["target_id"]
    if "params" in exp:
        assert decision.params == exp["params"]
