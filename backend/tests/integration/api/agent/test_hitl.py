"""Integration tests for /hitl agent route (app/api/routes/agent/hitl.py).

Covers the single endpoint ``POST /hitl/cancel`` across its three branches:
- no live session + no pending tool
- live running session (inject cancel into session loop)
- standalone (no live session) with a pending tool
"""

from __future__ import annotations

from types import SimpleNamespace

from .conftest import AsyncMethod, SyncMethod


class TestCancelHITL:
    async def test_cancel_no_pending_no_session(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            SimpleNamespace(get=lambda tid: None),
        )
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator",
            SimpleNamespace(get_pending_request=AsyncMethod(None)),
        )
        cleared = AsyncMethod(None)
        monkeypatch.setattr(
            "app.api.routes.agent.hitl.activity_monitor",
            SimpleNamespace(clear_human_request=cleared),
        )
        resp = await client.post(
            "/hitl/cancel", json={"thread_id": "t1", "model": "m1"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["request_id"] is None

    async def test_cancel_live_session(self, client, monkeypatch):
        session = SimpleNamespace(
            lifecycle="running",
            inject_resume=SyncMethod(None),
        )
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            SimpleNamespace(get=lambda tid: session),
        )
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator",
            SimpleNamespace(get_pending_request=AsyncMethod({"id": "p1", "name": "tool"})),
        )
        resp = await client.post(
            "/hitl/cancel", json={"thread_id": "t1", "model": "m1"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["request_id"] == "p1"

    async def test_cancel_live_session_no_pending_clears(self, client, monkeypatch):
        session = SimpleNamespace(
            lifecycle="running",
            inject_resume=SyncMethod(None),
        )
        cleared = AsyncMethod(None)
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            SimpleNamespace(get=lambda tid: session),
        )
        monkeypatch.setattr(
            "app.core.hitl.orchestrator.HITLOrchestrator",
            SimpleNamespace(get_pending_request=AsyncMethod(None)),
        )
        monkeypatch.setattr(
            "app.api.routes.agent.hitl.activity_monitor",
            SimpleNamespace(clear_human_request=cleared),
        )
        resp = await client.post(
            "/hitl/cancel", json={"thread_id": "t1", "model": "m1"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_cancel_pending_standalone(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.core.engine.session.manager.session_manager",
            SimpleNamespace(get=lambda tid: None),
        )
        hitl = SimpleNamespace(
            get_pending_request=AsyncMethod({"id": "p1", "name": "git_commit"}),
            handle_cancel=AsyncMethod("cancelled"),
        )
        monkeypatch.setattr("app.core.hitl.orchestrator.HITLOrchestrator", hitl)
        monkeypatch.setattr(
            "app.api.routes.agent.hitl.resume_agent_background", _noop_bg
        )
        resp = await client.post(
            "/hitl/cancel", json={"thread_id": "t1", "model": "m1"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["request_id"] == "p1"

    async def test_cancel_requires_thread_id(self, client):
        resp = await client.post("/hitl/cancel", json={"model": "m1"})
        assert resp.status_code == 422


async def _noop_bg(*_a, **_kw):
    return None
