"""executor.py terminal-status logic (design §16).

Mocks only the heavy collaborators at the fixture boundary (MacroEngine,
dispatch_agent_run, session) and asserts the pushed voice.route_result status
and summary — deterministic logic, per §14.1. Real macro playback is covered by
the §14.6 on-machine E2E, not here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.core.routing import executor
from app.core.routing.schemas import RouteDecision
from app.models.learning import LearnedSkill
from app.models.macro import Macro


class _FakeManager:
    def __init__(self):
        self.pushes = []

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


def _last_status(fake):
    tid, env = fake.pushes[-1]
    return tid, env["body"]["status"], env["body"]["summary"]


def _patch_manager(monkeypatch):
    fake = _FakeManager()
    monkeypatch.setattr(executor, "manager", fake)
    return fake


def _patch_session(monkeypatch, skill, macro=None):
    @asynccontextmanager
    async def fake_scope():
        class _S:
            async def get(self, model, sid):
                if model is LearnedSkill:
                    return skill
                if model is Macro:
                    return macro
                return None

        yield _S()

    monkeypatch.setattr(executor, "session_scope", fake_scope)


def _patch_macro_script(monkeypatch, sources):
    steps = [
        SimpleNamespace(
            type="dump",
            source=s,
            event_type=None,
            then_steps=[],
            else_steps=[],
            steps=[],
        )
        for s in sources
    ]

    def _from_yaml(_cls, _content):
        return SimpleNamespace(steps=steps)

    monkeypatch.setattr(
        "app.core.execution.macro.schemas.MacroScript.from_yaml",
        classmethod(lambda cls, content: _from_yaml(cls, content)),
    )


def _patch_macro_engine(monkeypatch, result):
    async def _execute(thread_id, _script, params=None):
        _execute.calls.append((thread_id, params))
        return result

    _execute.calls = []
    monkeypatch.setattr("app.core.execution.macro.engine.MacroEngine.execute", _execute)
    return _execute


def _patch_dispatch(monkeypatch, status="started", error=""):
    async def _dispatch(**kwargs):
        _dispatch.kwargs = kwargs
        return SimpleNamespace(status=status, inputs={"i": 1}, error=error)

    _dispatch.kwargs = None
    monkeypatch.setattr("app.core.engine.dispatch.dispatch_agent_run", _dispatch)

    async def _bg(thread_id, _inputs):
        _bg.calls.append(thread_id)

    _bg.calls = []
    monkeypatch.setattr("app.core.engine.background_agent.run_agent_background", _bg)
    return _dispatch, _bg


def _skill(name="播放音乐", desc="播放"):
    return SimpleNamespace(
        id=42,
        name=name,
        description=desc,
        parameters=[],
        macro_id=1,
        is_active=True,
        status="verified",
    )


def _macro():
    return SimpleNamespace(
        id=1,
        name="播放音乐",
        parameters=[],
        macro_script="steps: []",
        is_routable=lambda: True,
    )


@pytest.mark.asyncio
async def test_skill_deterministic_done(monkeypatch):
    fake = _patch_manager(monkeypatch)
    _patch_session(monkeypatch, _skill(), _macro())
    _patch_macro_script(monkeypatch, ["desktop"])
    _patch_macro_engine(monkeypatch, (True, "已为你播放", None))

    await executor.execute("t1", RouteDecision(
        target_type="skill", target={"id": 42}, params={"artist": "周杰伦"},
    ))

    tid, status, summary = _last_status(fake)
    assert tid == "t1" and status == "done" and summary == "已为你播放"


@pytest.mark.asyncio
async def test_skill_deterministic_failed_no_fallback(monkeypatch):
    fake = _patch_manager(monkeypatch)
    _patch_session(monkeypatch, _skill(), _macro())
    _patch_macro_script(monkeypatch, ["desktop"])
    _patch_macro_engine(monkeypatch, (False, "step 3 failed", None))
    dispatch, _bg = _patch_dispatch(monkeypatch)

    await executor.execute("t2", RouteDecision(target_type="skill", target={"id": 42}))

    tid, status, summary = _last_status(fake)
    assert status == "failed" and "step 3 failed" in summary
    assert dispatch.kwargs is None, "deterministic failure must not fall back to agent"


@pytest.mark.asyncio
async def test_skill_unsupported_macro_source(monkeypatch):
    fake = _patch_manager(monkeypatch)
    _patch_session(monkeypatch, _skill(), _macro())
    _patch_macro_script(monkeypatch, ["desktop", "mobile"])
    eng = _patch_macro_engine(monkeypatch, (True, "x", None))

    await executor.execute("t3", RouteDecision(target_type="skill", target={"id": 42}))

    tid, status, summary = _last_status(fake)
    assert status == "failed" and "unsupported macro source" in summary
    assert eng.calls == [], "MacroEngine must not run for non-DESKTOP voice macros"


@pytest.mark.asyncio
async def test_skill_not_found(monkeypatch):
    fake = _patch_manager(monkeypatch)
    _patch_session(monkeypatch, None)

    await executor.execute("t4", RouteDecision(target_type="skill", target={"id": 999}))

    tid, status, summary = _last_status(fake)
    assert status == "failed" and "not found" in summary


@pytest.mark.asyncio
async def test_agent_marks_registry_and_dispatches(monkeypatch):
    _patch_manager(monkeypatch)
    dispatch, bg = _patch_dispatch(monkeypatch, status="started")

    await executor.execute("t5", RouteDecision(
        target_type="agent", params={"task": "打开最新 PRD"},
    ))

    assert dispatch.kwargs is not None
    assert dispatch.kwargs["thread_id"] == "t5"
    assert dispatch.kwargs["metadata"]["source"] == "voice"
    import asyncio

    await asyncio.sleep(0)  # let the scheduled background task run once
    assert bg.calls == ["t5"], "agent background run must be scheduled"
    # registry holds the mark until finish.py consumes it
    assert await executor.consume_voice("t5") == "agent"
    assert await executor.consume_voice("t5") is None


@pytest.mark.asyncio
async def test_agent_dispatch_failed_pushes_failed(monkeypatch):
    fake = _patch_manager(monkeypatch)
    dispatch, bg = _patch_dispatch(monkeypatch, status="failed", error="no model")

    await executor.execute("t6", RouteDecision(target_type="agent", params={"task": "x"}))

    tid, status, summary = _last_status(fake)
    assert status == "failed" and "no model" in summary
    assert bg.calls == [], "background must not start when dispatch failed"
    assert await executor.consume_voice("t6") is None, "mark cleared on dispatch failure"


@pytest.mark.asyncio
async def test_local_is_noop(monkeypatch):
    fake = _patch_manager(monkeypatch)

    await executor.execute("t7", RouteDecision(target_type="local", target={"type": "local"}))

    assert fake.pushes == [], "local target produces no server-side done"


@pytest.mark.asyncio
async def test_finish_hook_pushes_done(monkeypatch):
    fake = _patch_manager(monkeypatch)
    await executor._mark_voice("t8", "agent")

    await executor.push_voice_result("t8", "done", "搞定了")

    tid, status, summary = _last_status(fake)
    assert tid == "t8" and status == "done" and summary == "搞定了"
