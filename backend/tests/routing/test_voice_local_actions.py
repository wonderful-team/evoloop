"""Exhaustive router-decision coverage for every voice-local action.

Layer-0 pattern matching (`暂停` -> `play_pause`) lives in the C++ client, so the
backend never sees raw templates. What the backend *does* own is the router
decision: given a high-confidence `local:{action}` candidate plus an LLM
`local_action` tool_call, it must route to `local` and pass the params through
unchanged. This test exercises that path for **every** registered voice-local
action so no action silently regresses (dropped params / wrong target).
"""

from __future__ import annotations

import pytest

from app.core.routing import router
from app.core.routing.init_spec import _VOICE_LOCAL_ACTIONS
from app.core.routing.schemas import RouteCandidate, RouteRequest

# Representative slot values per action; actions not listed use {} (no slots).
_EXAMPLE_PARAMS: dict[str, dict] = {
    "open_app": {"app": "微信"},
    "focus_app": {"app": "微信"},
    "quit_app": {"app": "微信"},
    "set_volume": {"delta": "+10"},
    "press_key": {"key": "Return"},
    "rename": {"name": "小E"},
}

# Build one case per registered action; play_pause is exercised with both states
# (pause / resume) since its two templates only differ by the `state` arg.
_CASES: list[tuple[str, dict]] = []
_seen: set[str] = set()
for _a in _VOICE_LOCAL_ACTIONS:
    _action = _a["id"]
    if _action in _seen:
        continue
    _seen.add(_action)
    if _action == "play_pause":
        _CASES.append(("play_pause", {"state": "pause"}))
        _CASES.append(("play_pause", {"state": "resume"}))
    else:
        _CASES.append((_action, dict(_EXAMPLE_PARAMS.get(_action, {}))))


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


def _patch_llm(monkeypatch, action: str, params: dict) -> None:
    tool_call = {"name": "local_action", "args": {"action": action, "params": params}}
    monkeypatch.setattr(router, "_min_score", lambda: 0.55)

    async def _create():
        return _FakeLLM(_Msg(tool_call))

    monkeypatch.setattr(router, "_create_route_llm", _create)


@pytest.mark.unit
@pytest.mark.parametrize("action,params", _CASES, ids=[f"{a}:{p}" for a, p in _CASES])
@pytest.mark.asyncio
async def test_every_voice_local_action_routes_local(action, params, monkeypatch):
    _patch_llm(monkeypatch, action, params)
    candidates = [RouteCandidate(id=f"local:{action}", type="local", name=action, score=0.9)]

    decision = await router.route(RouteRequest(text="x", thread_id="t"), candidates)

    assert decision.status == "routed"
    assert decision.target_type == "local"
    assert decision.target.get("id") == action  # router strips the `local:` prefix
    assert decision.params == params  # params must pass through unchanged


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hallucinated_local_action_delegates(monkeypatch):
    # LLM returns an action that is NOT among candidates -> must delegate to agent.
    tool_call = {"name": "local_action", "args": {"action": "fly", "params": {}}}
    monkeypatch.setattr(router, "_min_score", lambda: 0.55)

    async def _create():
        return _FakeLLM(_Msg(tool_call))

    monkeypatch.setattr(router, "_create_route_llm", _create)
    candidates = [RouteCandidate(id="local:open_app", type="local", name="open_app", score=0.9)]

    decision = await router.route(RouteRequest(text="飞", thread_id="t"), candidates)

    assert decision.target_type == "agent"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_candidates_delegates_without_llm(monkeypatch):
    async def _boom():
        raise AssertionError("LLM must not be called when there are no candidates")

    monkeypatch.setattr(router, "_min_score", lambda: 0.55)
    monkeypatch.setattr(router, "_create_route_llm", _boom)

    decision = await router.route(RouteRequest(text="任意", thread_id="t"), [])

    assert decision.target_type == "agent"
