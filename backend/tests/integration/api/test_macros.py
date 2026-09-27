# ruff: noqa: ARG001
"""Integration tests for the /macros API routes (app/api/routes/macros.py).

Exercises the real route layer (path/query parsing, request bodies, status
codes, response envelopes) via the shared API test harness, while mocking the
macro DAO/service boundaries.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.models.macro import Macro


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    """Yield a fake DB so route code that opens `session_scope()` resolves."""

    @asynccontextmanager
    async def _fake_scope():
        yield SimpleNamespace(db="fake")

    monkeypatch.setattr("app.api.routes.macros.session_scope", _fake_scope)


def _make_macro(macro_id: int = 1, **overrides) -> Macro:
    defaults = {
        "id": macro_id,
        "app_map_id": None,
        "entity": None,
        "name": "test-macro",
        "description": "desc",
        "trigger_patterns": [],
        "parameters": [],
        "risk_tier": "observe",
        "requires_confirmation": False,
        "allow_self_healing": False,
        "status": "active",
        "is_active": True,
        "namespace": None,
        "domain": None,
        "fallback_skill_id": None,
        "project_id": None,
        "macro_script": "steps: []",
        "app_map_version": None,
        "source_thread_id": None,
    }
    defaults.update(overrides)
    return Macro(**defaults)


async def _publish_macro_mutated(*args, **kwargs):
    return None


async def _load_macro(macro_id, *args, **kwargs):
    if macro_id == 99:
        return None
    return _make_macro(macro_id)


async def _list_macros_dao(**kwargs):
    return [_make_macro(1), _make_macro(2)]


async def _update_macro_dao(*args, **kwargs):
    return True


async def _delete_macro_dao(*args, **kwargs):
    return True


async def _confirm_macro_dao(*args, **kwargs):
    return True


async def _confirm_bulk_dao(macro_ids):
    return len(macro_ids)


async def _create_macro_from_synthesis(**kwargs):
    return SimpleNamespace(id=7)


class TestMacroCRUD:
    @pytest.mark.parametrize("method,path,status", [
        ("POST", "/macros/", 201),
        ("GET", "/macros/", 200),
        ("GET", "/macros/1", 200),
        ("GET", "/macros/99", 404),
        ("PUT", "/macros/1", 200),
        ("DELETE", "/macros/1", 200),
        ("DELETE", "/macros/99", 404),
        ("POST", "/macros/1/confirm", 200),
        ("POST", "/macros/99/confirm", 404),
    ])
    async def test_response_status(
        self, client, monkeypatch, method, path, status
    ):
        monkeypatch.setattr(
            "app.api.routes.macros.create_macro_from_synthesis",
            _create_macro_from_synthesis,
        )
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        monkeypatch.setattr("app.api.routes.macros.list_macros_dao", _list_macros_dao)
        monkeypatch.setattr(
            "app.api.routes.macros.update_macro_dao", _update_macro_dao
        )
        monkeypatch.setattr(
            "app.api.routes.macros.delete_macro_dao", _delete_macro_dao
        )
        monkeypatch.setattr(
            "app.api.routes.macros.confirm_macro_dao", _confirm_macro_dao
        )
        monkeypatch.setattr(
            "app.api.routes.macros.publish_macro_mutated", _publish_macro_mutated
        )
        if path.endswith("/99") and method == "DELETE":
            async def _del_missing(*args, **kwargs):
                return False
            monkeypatch.setattr("app.api.routes.macros.delete_macro_dao", _del_missing)
        if path.endswith("/99/confirm"):
            async def _confirm_missing(*args, **kwargs):
                return False
            monkeypatch.setattr("app.api.routes.macros.confirm_macro_dao", _confirm_missing)

        body = None
        if method == "POST":
            body = {"name": "x", "macro_script": "steps: []"}
        if method == "PUT":
            body = {"name": "renamed"}
        resp = await client.request(method, path, json=body)
        assert resp.status_code == status

    async def test_create_macro(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.create_macro_from_synthesis",
            _create_macro_from_synthesis,
        )
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        monkeypatch.setattr(
            "app.api.routes.macros.publish_macro_mutated", _publish_macro_mutated
        )
        resp = await client.post(
            "/macros/", json={"name": "my-macro", "macro_script": "steps: []"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-macro"
        assert data["id"] == 7

    async def test_list_macros(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.list_macros_dao", _list_macros_dao
        )
        resp = await client.get("/macros/?project_id=1&limit=5")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_macro_returns_detail(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        resp = await client.get("/macros/3")
        assert resp.status_code == 200
        assert resp.json()["id"] == 3
        assert "macro_script" in resp.json()

    async def test_get_macro_404(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        resp = await client.get("/macros/99")
        assert resp.status_code == 404

    async def test_update_macro(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.update_macro_dao", _update_macro_dao
        )
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        resp = await client.put("/macros/5", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-macro"

    async def test_update_macro_invalid_yaml_400(self, client, monkeypatch):
        def fake_validate(script):
            return False, "bad yaml", None
        monkeypatch.setattr(
            "app.core.learning.macro.authoring.validate_macro_structure",
            fake_validate,
        )
        resp = await client.put("/macros/5", json={"macro_script": "steps: [[["})
        assert resp.status_code == 400

    async def test_update_macro_404(self, client, monkeypatch):
        async def _no_update(*args, **kwargs):
            return False
        monkeypatch.setattr("app.api.routes.macros.update_macro_dao", _no_update)
        resp = await client.put("/macros/99", json={"name": "x"})
        assert resp.status_code == 404

    async def test_delete_macro(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.delete_macro_dao", _delete_macro_dao
        )
        resp = await client.delete("/macros/5")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    async def test_confirm_macro(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.confirm_macro_dao", _confirm_macro_dao
        )
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        resp = await client.post("/macros/5/confirm")
        assert resp.status_code == 200

    async def test_confirm_bulk(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.macros.confirm_bulk_dao", _confirm_bulk_dao
        )
        resp = await client.post(
            "/macros/confirm-bulk", json={"macro_ids": [1, 2, 3]}
        )
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == 3

    async def test_execute_macro(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        result = SimpleNamespace(
            success=True,
            message="ok",
            extracted_data={"a": 1},
            status="completed",
            step_log=None,
        )

        async def _run(*args, **kwargs):
            return result

        monkeypatch.setattr("app.api.routes.macros.MacroEngine.run", _run)
        resp = await client.post(
            "/macros/5/execute",
            json={"thread_id": "t-1", "params": {"speed": 3}},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_execute_macro_404(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.macros.load_macro", _load_macro)
        resp = await client.post("/macros/99/execute", json={})
        assert resp.status_code == 404

    async def test_maintenance_queues_task(self, client, monkeypatch):
        dispatched = {}

        class FakeTask:
            @staticmethod
            def delay(**kwargs):
                dispatched.update(kwargs)

        monkeypatch.setattr(
            "app.core.learning.macro.tasks.native_macro_maintenance_task",
            FakeTask,
        )
        resp = await client.post(
            "/macros/maintenance", json={"apps": ["com.foo:MyApp"]}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["queued"] is True
        assert dispatched["apps"] == [("com.foo", "MyApp")]
