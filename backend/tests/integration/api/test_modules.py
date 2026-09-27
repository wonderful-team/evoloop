"""Integration tests for the /modules API routes (app/api/routes/modules.py)."""

from __future__ import annotations

from types import SimpleNamespace


class TestListModules:
    async def test_success(self, client, monkeypatch):
        from app.domain.codebase.generation.module_graph import module_graph_service

        mod = SimpleNamespace(
            name="auth",
            entities=["login", "token"],
            entity_count=2,
            summary="Auth module",
        )
        async def _get_modules(_pid):
            return [mod]

        monkeypatch.setattr(module_graph_service, "get_modules", _get_modules)
        resp = await client.get("/api/v1/projects/1/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "auth"
        assert data[0]["entity_count"] == 2

    async def test_empty(self, client, monkeypatch):
        from app.domain.codebase.generation.module_graph import module_graph_service

        async def _get_modules(_pid):
            return []

        monkeypatch.setattr(module_graph_service, "get_modules", _get_modules)
        resp = await client.get("/api/v1/projects/1/modules")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetModuleOf:
    async def test_success(self, client, monkeypatch):
        from app.domain.codebase.generation.module_graph import module_graph_service

        async def _get_module_of(_pid, _ent):
            return "auth"

        monkeypatch.setattr(module_graph_service, "get_module_of", _get_module_of)
        resp = await client.get("/api/v1/projects/1/modules/login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity"] == "login"
        assert data["module"] == "auth"

    async def test_not_found(self, client, monkeypatch):
        from app.domain.codebase.generation.module_graph import module_graph_service

        async def _get_module_of(_pid, _ent):
            return None

        monkeypatch.setattr(module_graph_service, "get_module_of", _get_module_of)
        resp = await client.get("/api/v1/projects/1/modules/unknown")
        assert resp.status_code == 200
        assert resp.json()["module"] is None
