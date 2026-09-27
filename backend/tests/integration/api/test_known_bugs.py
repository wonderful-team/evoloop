"""Live-session injection regression tests.

验证 /chat/resume 与 /hitl/cancel 在活会话（running）分支下，把用户输入 /
HITL 决策 / 取消信号**送达**运行中的会话主循环（gate 事件队列）。

注：``session.inject_user_message`` / ``session.inject_resume`` 是**同步**方法
（内部 ``gate.put_nowait`` 立即入队），并非 async——所以调用方不需要 await。
这里的 mock 用同步计数实现，断言"同步调用确实发生且入队"。
"""

from __future__ import annotations

from types import SimpleNamespace

# ruff: noqa: ARG001


class TracedSyncMethod:
    """Sync method that records how many times its body actually RAN.

    Matches production ``AgentSession.inject_*`` (sync, ``gate.put_nowait``).
    """

    def __init__(self):
        self.calls = 0
        self.last_payload: dict | None = None

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.last_payload = kwargs or (args[0] if args else None)
        return None


class _FakeSharedState:
    def __init__(self):
        self.active = 0

    async def get_active_project_id(self):
        return self.active

    async def set_active_project_id(self, project_id):
        self.active = project_id


def _live_session():
    return SimpleNamespace(
        lifecycle="running",
        inject_user_message=TracedSyncMethod(),
        inject_resume=TracedSyncMethod(),
    )


def _running_session_manager(session):
    fake = SimpleNamespace()
    fake.get = lambda thread_id: session
    return fake


class TestChatResumeLiveSessionInjection:
    """/chat/resume 在活会话分支：输入/HITL 决策必须送达会话主循环。"""

    async def test_resume_new_message_is_delivered(self, client, monkeypatch):
        session = _live_session()
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            _running_session_manager(session),
        )
        monkeypatch.setattr("app.core.state.shared_state", _FakeSharedState())
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
            _no_pending,
        )
        monkeypatch.setattr(
            "app.core.engine.dispatch.persist_user_message", _no_pending
        )

        resp = await client.post(
            "/chat/resume", json={"thread_id": "t1", "user_input": "hi", "model": "m1"}
        )
        assert resp.status_code == 200
        # 无 pending → 走 inject_user_message（同步入队）。正确契约：恰好一次送达。
        assert session.inject_user_message.calls == 1

    async def test_resume_hitl_decision_is_delivered(self, client, monkeypatch):
        session = _live_session()
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            _running_session_manager(session),
        )
        monkeypatch.setattr("app.core.state.shared_state", _FakeSharedState())
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
            _pending,
        )

        resp = await client.post(
            "/chat/resume", json={"thread_id": "t1", "user_input": "ok", "model": "m1"}
        )
        assert resp.status_code == 200
        # 有 pending → 走 inject_resume（同步入队）。正确契约：恰好一次送达。
        assert session.inject_resume.calls == 1


class TestHitlCancelLiveSessionInjection:
    """/hitl/cancel 在活会话分支：取消信号必须送达运行中的会话。"""

    async def test_cancel_decision_is_delivered(self, client, monkeypatch):
        session = _live_session()
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            _running_session_manager(session),
        )
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
            _pending,
        )

        resp = await client.post(
            "/hitl/cancel", json={"thread_id": "t1", "model": "m1"}
        )
        assert resp.status_code == 200
        # 取消 → 走 inject_resume(is_cancel=True)（同步入队）。正确契约：恰好一次送达。
        assert session.inject_resume.calls == 1


async def _no_pending(*args, **kwargs):
    return None


async def _pending(*args, **kwargs):
    return {"id": "req-1", "name": "bash", "project_id": 1}
