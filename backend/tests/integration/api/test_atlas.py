"""Integration tests for the atlas routes (app/api/routes/atlas.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


async def _async_return(value):
    return value


async def _no_value():
    return None


class TestGenerateAppMap:
    async def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.atlas.get_project_path",
            lambda pid: _async_return(None),
        )
        resp = await client.post(
            "/atlas/app-maps/generate",
            json={"project_id": 999, "entity": "auth"},
        )
        assert resp.status_code == 404

    async def test_path_not_dir(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.atlas.get_project_path",
            lambda pid: _async_return("/no/such/path"),
        )
        import os

        monkeypatch.setattr(os.path, "isdir", lambda p: False)
        resp = await client.post(
            "/atlas/app-maps/generate",
            json={"project_id": 1, "entity": "auth"},
        )
        assert resp.status_code == 400

    async def test_empty_entity(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.atlas.get_project_path",
            lambda pid: _async_return("/tmp"),
        )
        import os

        monkeypatch.setattr(os.path, "isdir", lambda p: True)
        resp = await client.post(
            "/atlas/app-maps/generate",
            json={"project_id": 1, "entity": ""},
        )
        assert resp.status_code == 400

    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.atlas.get_project_path",
            lambda pid: _async_return("/tmp/proj"),
        )
        import os

        monkeypatch.setattr(os.path, "isdir", lambda p: True)
        monkeypatch.setattr("app.api.routes.atlas.unique_id", lambda *a: "t-1")
        monkeypatch.setattr(
            "app.api.routes.atlas._ensure_app_map_analysis_skill",
            _no_value,
        )

        from app.core.engine.dispatch import DispatchStatus

        result = SimpleNamespace(
            status=DispatchStatus.QUEUED,
            inputs={"thread_id": "t-1"},
            error=None,
        )
        monkeypatch.setattr(
            "app.api.routes.atlas.dispatch_agent_run",
            lambda **kw: _async_return(result),
        )
        monkeypatch.setattr(
            "app.api.routes.atlas.run_agent_background",
            lambda *a, **k: None,
        )

        resp = await client.post(
            "/atlas/app-maps/generate",
            json={"project_id": 1, "entity": "auth"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["task_id"] == "t-1"

    async def test_dispatch_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.atlas.get_project_path",
            lambda pid: _async_return("/tmp"),
        )
        import os

        monkeypatch.setattr(os.path, "isdir", lambda p: True)
        monkeypatch.setattr("app.api.routes.atlas.unique_id", lambda *a: "t-1")
        monkeypatch.setattr(
            "app.api.routes.atlas._ensure_app_map_analysis_skill",
            _no_value,
        )
        from app.core.engine.dispatch import DispatchStatus

        result = SimpleNamespace(status=DispatchStatus.FAILED, inputs={}, error="boom")
        monkeypatch.setattr(
            "app.api.routes.atlas.dispatch_agent_run",
            lambda **kw: _async_return(result),
        )
        resp = await client.post(
            "/atlas/app-maps/generate",
            json={"project_id": 1, "entity": "auth"},
        )
        assert resp.status_code == 500


class TestListAppMaps:
    async def test_empty(self, client, monkeypatch):
        async def _list_maps(_pid, **kwargs):
            _ = kwargs
            return []

        monkeypatch.setattr(
            "app.core.atlas.source.persistence.list_app_maps", _list_maps
        )
        monkeypatch.setattr(
            "app.api.routes.atlas.list_macros",
            lambda **_kwargs: [],
        )
        resp = await client.get("/atlas/app-maps?project_id=1")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_maps(self, client, monkeypatch):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        app_map = SimpleNamespace(
            id="am-1",
            project_id=1,
            entity="auth",
            platform="android",
            map_version="1.0",
            status="active",
            content_hash="abc",
            actions=[{"name": "login"}, {"name": "logout"}],
            created_at=now,
        )

        async def _list_maps(_pid, **kwargs):
            _ = kwargs
            return [app_map]

        monkeypatch.setattr(
            "app.core.atlas.source.persistence.list_app_maps", _list_maps
        )

        async def _macros(**_kwargs):
            _ = _kwargs
            return [
                SimpleNamespace(id="m1", status="verified"),
                SimpleNamespace(id="m2", status="pending_review"),
            ]

        monkeypatch.setattr("app.api.routes.atlas.list_macros", _macros)
        resp = await client.get("/atlas/app-maps?project_id=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["actions_count"] == 2
        assert data[0]["macro_count"] == 2
        assert data[0]["pending_count"] == 1
