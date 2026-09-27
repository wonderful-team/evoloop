"""Integration tests for conversations/conversations.py routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest  # noqa: F401


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    @asynccontextmanager
    async def _fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr(
        "app.api.routes.conversations.conversations.session_scope", _fake_scope
    )


class TestListConversations:
    async def test_empty_list(self, client, monkeypatch):
        class _Exec:
            def scalar(self_inner):
                return 0

            def scalars(self_inner):
                return SimpleNamespace(all=lambda: [])

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.activity_monitor",
            SimpleNamespace(get_statuses=AsyncStub({})),
        )
        resp = await client.get("/conversations/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 0

    async def test_list_with_conversations(self, client, monkeypatch):
        convs = [_make_conversation("t-1"), _make_conversation("t-2")]

        class _Exec:
            def scalar(self_inner):
                return 2

            def scalars(self_inner):
                return SimpleNamespace(all=lambda: convs)

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.activity_monitor",
            SimpleNamespace(get_statuses=AsyncStub({"t-1": {"status": "running"}})),
        )
        resp = await client.get("/conversations/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["thread_id"] == "t-1"
        assert data["data"][0]["status"] == "running"

    async def test_list_with_project_filter(self, client, monkeypatch):
        convs = [_make_conversation("t-1", project_id=5)]

        class _Exec:
            def scalar(self_inner):
                return 1

            def scalars(self_inner):
                return SimpleNamespace(all=lambda: convs)

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.activity_monitor",
            SimpleNamespace(get_statuses=AsyncStub({})),
        )
        resp = await client.get("/conversations/?project_id=5")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestUpdateConversation:
    async def test_update_title(self, client, monkeypatch):
        conv = _make_conversation("t-1", title="old")

        async def _get(_model, _tid):
            return conv

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        resp = await client.patch("/conversations/t-1", json={"title": "new"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "new"
        assert resp.json()["status"] == "updated"

    async def test_update_pin(self, client, monkeypatch):
        conv = _make_conversation("t-1", is_pinned=False)

        async def _get(_model, _tid):
            return conv

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        resp = await client.patch("/conversations/t-1", json={"is_pinned": True})
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    async def test_not_found(self, client, monkeypatch):
        async def _get(_model, _tid):
            return None

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        resp = await client.patch("/conversations/missing", json={"title": "x"})
        assert resp.status_code == 404

    async def test_access_denied(self, client, monkeypatch):
        conv = _make_conversation("t-1", member_id=999)

        async def _get(_model, _tid):
            return conv

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        resp = await client.patch("/conversations/t-1", json={"title": "x"})
        assert resp.status_code == 403


class TestGetThreadActivity:
    async def test_get_activity(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.activity_monitor",
            SimpleNamespace(
                get_activity=AsyncStub({"status": "idle", "goal": None})
            ),
        )
        resp = await client.get("/conversations/t-1/activity")
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"


class TestDeleteConversation:
    async def test_delete_success(self, client, monkeypatch):
        conv = _make_conversation("t-1")

        async def _get(_model, _tid):
            return conv

        async def _delete(_obj):
            pass

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, delete=_delete, flush=_flush)),
        )
        monkeypatch.setattr(
            "app.core.engine.event.publishers.publish_conversation_deleted",
            AsyncStub(None),
        )
        resp = await client.delete("/conversations/t-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    async def test_delete_access_denied(self, client, monkeypatch):
        conv = _make_conversation("t-1", member_id=999)

        async def _get(_model, _tid):
            return conv

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        resp = await client.delete("/conversations/t-1")
        assert resp.status_code == 403

    async def test_delete_not_found_still_returns_deleted(self, client, monkeypatch):
        async def _get(_model, _tid):
            return None

        async def _flush():
            pass

        monkeypatch.setattr(
            "app.api.routes.conversations.conversations.session_scope",
            lambda: _ctx(SimpleNamespace(get=_get, flush=_flush)),
        )
        monkeypatch.setattr(
            "app.core.engine.event.publishers.publish_conversation_deleted",
            AsyncStub(None),
        )
        resp = await client.delete("/conversations/missing")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):  # noqa: ARG002
        return self._value


def _make_conversation(
    thread_id: str = "t-1",
    *,
    title: str = "test-conv",
    project_id: int | None = None,
    member_id: int = 1,
    is_pinned: bool = False,
):
    now = datetime.now()
    return SimpleNamespace(
        id=thread_id,
        title=title,
        project_id=project_id,
        member_id=member_id,
        updated_at=now,
        is_pinned=is_pinned,
        parent_thread_id=None,
        root_thread_id=None,
        caller_device_key=None,
        executor_device_key=None,
        executor_device_name=None,
    )


@asynccontextmanager
async def _ctx(session):
    yield session
