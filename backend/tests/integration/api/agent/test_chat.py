"""Integration tests for /chat agent routes (app/api/routes/agent/chat.py).

Covers all 5 endpoints:
- POST /chat
- POST /chat/stop
- POST /agent/stop
- POST /chat/retry
- POST /chat/resume

Routes that lazily import singletons are mocked on their source modules.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.core.engine.dispatch import DispatchResult, DispatchStatus
from app.core.routing.actions import ActionOutcome
from app.core.routing.dispatch_handler import DispatchOutcome

from .conftest import AsyncMethod, SyncMethod


@pytest.fixture(autouse=True)
def _mock_route_lock_scope(monkeypatch):
    """chat_endpoint uses ``async with route_lock_scope(...)``."""

    @asynccontextmanager
    async def _fake_scope(*_a, **_kw):
        yield

    monkeypatch.setattr("app.api.routes.agent.chat.route_lock_scope", _fake_scope)


class TestChatEndpoint:
    async def test_chat_handled_local_path(self, client, monkeypatch, patched_shared_state):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(
                handled=True,
                local_response=ActionOutcome(ok=True, message="all good", action_type="local"),
            )

        end_run = AsyncMethod(None)
        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        monkeypatch.setattr(
            "app.api.routes.agent.chat.activity_monitor",
            SimpleNamespace(end_run=end_run),
        )

        resp = await client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["action_type"] == "local"
        assert "thread_id" in data

    async def test_chat_navigate_local_path(
        self, client, monkeypatch, patched_shared_state
    ):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(
                handled=True,
                local_response=ActionOutcome(
                    ok=True, message="nav", action_type="navigate", data={"route": "/x"}
                ),
            )

        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        monkeypatch.setattr(
            "app.api.routes.agent.chat.activity_monitor",
            SimpleNamespace(end_run=AsyncMethod(None)),
        )
        resp = await client.post("/chat", json={"message": "go"})
        assert resp.status_code == 200
        assert resp.json()["navigate"] == "/x"

    async def test_chat_queued_path(self, client, monkeypatch, patched_shared_state, patched_session_manager):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(
                handled=False,
                msg=object(),
                inputs=DispatchResult(
                    status=DispatchStatus.QUEUED,
                    thread_id="t1",
                    message_id="m1",
                    inputs={"goal": "x"},
                ),
            )

        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        monkeypatch.setattr(
            "app.api.routes.agent.chat.activity_monitor",
            SimpleNamespace(end_run=AsyncMethod(None)),
        )
        resp = await client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["message_id"] == "m1"

    async def test_chat_queued_uses_set_active_project_id(
        self, client, monkeypatch, patched_shared_state, patched_session_manager
    ):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(
                handled=False,
                msg=object(),
                inputs=DispatchResult(
                    status=DispatchStatus.QUEUED,
                    thread_id="t1",
                    message_id="m1",
                    inputs={"goal": "x"},
                ),
            )

        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        monkeypatch.setattr(
            "app.api.routes.agent.chat.activity_monitor",
            SimpleNamespace(end_run=AsyncMethod(None)),
        )
        resp = await client.post("/chat", json={"message": "hi", "project_id": 42})
        assert resp.status_code == 200
        assert patched_shared_state.active == 42

    async def test_chat_invalid_request_400(self, client, monkeypatch, patched_shared_state):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(handled=False, msg=None, inputs=None)

        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        resp = await client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 400

    async def test_chat_dispatch_failed_500(self, client, monkeypatch, patched_shared_state):
        async def _dispatch(*_a, **_kw):
            return DispatchOutcome(
                handled=False,
                msg=object(),
                inputs=DispatchResult(
                    status=DispatchStatus.FAILED,
                    thread_id="t1",
                    error="boom",
                ),
            )

        monkeypatch.setattr("app.api.routes.agent.chat.dispatch_user_message", _dispatch)
        resp = await client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500


class TestStopChat:
    async def test_stop_chat(self, client, patched_session_manager):
        resp = await client.post("/chat/stop", json={"thread_id": "t1", "message": "m"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopping"
        assert data["thread_id"] == "t1"

    async def test_stop_chat_requires_thread_id(self, client, patched_session_manager):
        resp = await client.post("/chat/stop", json={"message": "m"})
        assert resp.status_code == 400


class TestStopAllAgent:
    async def test_stop_all_agent_thread(self, client, monkeypatch):
        sm = SimpleNamespace(stop_agent=AsyncMethod(None))
        monkeypatch.setattr("app.core.engine.session.manager.session_manager", sm)
        resp = await client.post("/agent/stop", params={"thread_id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["thread_id"] == "t1"

    async def test_stop_all_agent_project(self, client, monkeypatch):
        sm = SimpleNamespace(stop_all=AsyncMethod(None))
        ar = SimpleNamespace(cancel_all=AsyncMethod(None))
        prov = SimpleNamespace(stop_project=AsyncMethod(None), stop_global=AsyncMethod(None))
        monkeypatch.setattr("app.core.engine.session.manager.session_manager", sm)
        monkeypatch.setattr("app.core.engine.agent_run_registry.agent_run_registry", ar)
        monkeypatch.setattr("app.core.channel.duty.provision", prov)
        resp = await client.post("/agent/stop", params={"project_id": 5})
        assert resp.status_code == 200

    async def test_stop_all_agent_global(self, client, monkeypatch):
        sm = SimpleNamespace(stop_all=AsyncMethod(None))
        ar = SimpleNamespace(cancel_all=AsyncMethod(None))
        prov = SimpleNamespace(stop_project=AsyncMethod(None), stop_global=AsyncMethod(None))
        identity = SimpleNamespace(resolve_member_id_from_token=AsyncMethod(7))
        monkeypatch.setattr("app.core.engine.session.manager.session_manager", sm)
        monkeypatch.setattr("app.core.engine.agent_run_registry.agent_run_registry", ar)
        monkeypatch.setattr("app.core.channel.duty.provision", prov)
        monkeypatch.setattr("app.core.identity.identity_service", identity)
        resp = await client.post("/agent/stop")
        assert resp.status_code == 200
        assert resp.json()["thread_id"] == ""


class _FakeRewindResult:
    def __init__(self, status="success", reverted_file_count=0, removed_message_count=0, errors=None):
        self.status = status
        self.reverted_file_count = reverted_file_count
        self.removed_message_count = removed_message_count
        self.errors = errors or []


class TestRetryChat:
    async def test_retry_requires_thread_id(self, client, monkeypatch):
        resp = await client.post("/chat/retry", json={"message": "m"})
        assert resp.status_code == 400

    async def test_retry_no_human_message_404(self, client, monkeypatch, patched_shared_state):
        class _Session:
            async def execute(self, stmt):
                return _ResultStub()

        @asynccontextmanager
        async def _scope():
            yield _Session()

        monkeypatch.setattr("app.infrastructure.database.session_scope", _scope)
        resp = await client.post("/chat/retry", json={"thread_id": "t1", "message": "m"})
        assert resp.status_code == 404

    async def test_retry_success(self, client, monkeypatch, patched_shared_state, patched_session_manager):
        human_msg = SimpleNamespace(
            id=10, thread_id="t1", role="human", content="hello", references=None,
            meta_data={}, source=None, project_id=1,
        )

        class _Session:
            async def execute(self, stmt):
                return _ResultStub(human_msg)

        @asynccontextmanager
        async def _scope():
            yield _Session()

        monkeypatch.setattr("app.infrastructure.database.session_scope", _scope)
        monkeypatch.setattr(
            "app.core.channel.input.web_input.web_input",
            SimpleNamespace(
                receive=AsyncMethod(
                    SimpleNamespace(
                        source="web",
                        project_id=1,
                        member_id=0,
                        text="m",
                        metadata={},
                        thread_id="t1",
                    )
                ),
                dispatch=AsyncMethod(
                    SimpleNamespace(status="queued", inputs={"goal": "x"}, message_id="mid", error=None)
                ),
            ),
        )
        # retry_service 顶层绑定了 perform_rewind —— 源模块 + 消费方引用都要 mock
        monkeypatch.setattr("app.core.engine.rewind.perform_rewind", _rewind_success)
        monkeypatch.setattr("app.core.engine.retry_service.perform_rewind", _rewind_success)

        resp = await client.post("/chat/retry", json={"thread_id": "t1", "message": "m"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["action"] == "retry"


async def _rewind_success(*_a, **_kw):
    return _FakeRewindResult()


class _ResultStub:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class TestResumeChat:
    async def test_resume_chat_no_live_session(self, client, monkeypatch, patched_shared_state, patched_session_manager):
        hitl = SimpleNamespace(get_pending_request=AsyncMethod(None))
        monkeypatch.setattr("app.core.hitl.orchestrator.HITLOrchestrator", hitl)
        monkeypatch.setattr("app.api.routes.agent.chat.resume_agent_background", _noop_bg)
        resp = await client.post(
            "/chat/resume", json={"thread_id": "t1", "message": "m", "model": "m1"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resuming"
        assert data["thread_id"] == "t1"

    async def test_resume_chat_live_session(self, client, monkeypatch, patched_shared_state, patched_session_manager):
        live_session = SimpleNamespace(lifecycle="running", inject_resume=SyncMethod(None), inject_user_message=SyncMethod(None))
        patched_session_manager.return_get = live_session
        hitl = SimpleNamespace(
            get_pending_request=AsyncMethod(None),
        )
        monkeypatch.setattr("app.core.hitl.orchestrator.HITLOrchestrator", hitl)
        monkeypatch.setattr("app.core.engine.dispatch.persist_user_message", _noop_async)
        resp = await client.post(
            "/chat/resume", json={"thread_id": "t1", "message": "m", "model": "m1"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resuming"


async def _noop_bg(*_a, **_kw):
    return None


async def _noop_async(*_a, **_kw):
    return None
