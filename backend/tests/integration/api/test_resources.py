"""Integration tests for the resources routes (app/api/routes/resources.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace


class _FakeResult:
    def __init__(self, scalars=None):
        self._scalars = scalars or []

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars)

    def scalar_one_or_none(self):
        return self._scalars[0] if self._scalars else None


class TestListResources:
    async def test_empty_list(self, client, monkeypatch):
        @asynccontextmanager
        async def _scope():
            session = SimpleNamespace(
                execute=lambda stmt: _FakeResult([]),
            )
            yield session

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.get("/projects/1/resources")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateResource:
    async def test_create_success(self, client, monkeypatch):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)

        class FakeSession:
            async def execute(self, stmt):
                return _FakeResult([])

            def add(self, obj):
                self._resource = obj

            async def commit(self):
                pass

            async def refresh(self, obj):
                obj.id = 1
                obj.created_at = now

        @asynccontextmanager
        async def _scope():
            yield FakeSession()

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.post(
            "/projects/1/resources",
            json={"type": "link", "name": "docs", "content": "https://docs.example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["name"] == "docs"

    async def test_create_file_idempotent(self, client, monkeypatch):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        existing = SimpleNamespace(
            id=5, project_id=1, type="file", name="readme.md",
            content="README.md", created_at=now,
        )

        class FakeSession:
            async def execute(self, stmt):
                return _FakeResult([existing])

        @asynccontextmanager
        async def _scope():
            yield FakeSession()

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.post(
            "/projects/1/resources",
            json={"type": "file", "name": "readme.md", "content": "README.md"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == 5


class TestDeleteResource:
    async def test_delete_success(self, client, monkeypatch):
        resource = SimpleNamespace(
            id=10, project_id=1, type="link", name="x", content="http://x"
        )

        class FakeSession:
            async def get(self, model, rid):
                if rid == 10:
                    return resource
                return None

            async def delete(self, obj):
                pass

        @asynccontextmanager
        async def _scope():
            yield FakeSession()

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.delete("/projects/1/resources/10")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_delete_not_found_returns_success(self, client, monkeypatch):
        class FakeSession:
            async def get(self, model, rid):
                return None

            async def delete(self, obj):
                pass

        @asynccontextmanager
        async def _scope():
            yield FakeSession()

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.delete("/projects/1/resources/999")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_delete_wrong_project_403(self, client, monkeypatch):
        resource = SimpleNamespace(
            id=10, project_id=2, type="link", name="x", content="http://x"
        )

        class FakeSession:
            async def get(self, model, rid):
                if rid == 10:
                    return resource
                return None

            async def delete(self, obj):
                pass

        @asynccontextmanager
        async def _scope():
            yield FakeSession()

        monkeypatch.setattr(
            "app.api.routes.resources.session_scope", _scope
        )
        resp = await client.delete("/projects/1/resources/10")
        assert resp.status_code == 403
