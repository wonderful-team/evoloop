"""Integration tests for projects/duty.py routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest  # noqa: F401


class TestGetProjectDuty:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty",
            AsyncStub(
                (
                    "/ws/proj",
                    {
                        "enabled": True,
                        "channels": {"wecom": {}},
                    },
                )
            ),
        )
        resp = await client.get("/projects/1/duty")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["channels"] == {"wecom": {}}

    async def test_project_not_found(self, client, monkeypatch):
        async def _load_duty(_pid):
            from fastapi import HTTPException

            raise HTTPException(404, "Project not found or has no local path")

        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty", _load_duty
        )
        resp = await client.get("/projects/999/duty")
        assert resp.status_code == 404

    async def test_empty_duty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty",
            AsyncStub(("/ws/proj", {})),
        )
        resp = await client.get("/projects/1/duty")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is None


class TestUpdateProjectDuty:
    async def test_partial_update(self, client, monkeypatch):
        saved = {}

        async def _load_duty(_pid):
            return "/ws/proj", saved

        def _write(_path, data):
            saved.update(data.get("customer_service_duty", {}))

        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty", _load_duty
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.write_project_json", _write
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.read_project_json",
            lambda _path: {"customer_service_duty": saved},
        )

        resp = await client.put(
            "/projects/1/duty",
            json={"channels": {"wecom": {"enabled": True}}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["channels"]["wecom"]["enabled"] is True

    async def test_enabled_true_starts_duty(self, client, monkeypatch):
        saved = {"enabled": False}

        async def _load_duty(_pid):
            return "/ws/proj", saved

        def _write(_path, data):
            saved.update(data.get("customer_service_duty", {}))

        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty", _load_duty
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.write_project_json", _write
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.read_project_json",
            lambda _path: {"customer_service_duty": saved},
        )

        monkeypatch.setattr(
            "app.core.channel.duty.provision.start_project",
            AsyncStub({"success": True}),
        )
        monkeypatch.setattr(
            "app.core.channel.duty.provision.stop_project", AsyncStub({})
        )

        resp = await client.put(
            "/projects/1/duty",
            json={"enabled": True},
        )
        assert resp.status_code == 200

    async def test_enabled_true_start_fails_400(self, client, monkeypatch):
        saved = {"enabled": False}

        async def _load_duty(_pid):
            return "/ws/proj", saved

        def _write(_path, data):
            saved.update(data.get("customer_service_duty", {}))

        monkeypatch.setattr(
            "app.api.routes.projects.duty._load_duty", _load_duty
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.write_project_json", _write
        )
        monkeypatch.setattr(
            "app.api.routes.projects.duty.read_project_json",
            lambda _path: {"customer_service_duty": saved},
        )

        monkeypatch.setattr(
            "app.core.channel.duty.provision.start_project",
            AsyncStub({"success": False, "errors": ["channel not configured"]}),
        )

        resp = await client.put(
            "/projects/1/duty",
            json={"enabled": True},
        )
        assert resp.status_code == 400
        assert saved.get("enabled") is False


class TestGetProjectDutyStatus:
    async def test_success(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.projects.duty.get_project_path",
            AsyncStub(str(tmp_path)),
        )

        monkeypatch.setattr(
            "app.api.routes.projects.listing._read_duty_status",
            AsyncStub({"enabled": True, "active": False}),
        )

        class _Exec:
            def scalars(self):
                return SimpleNamespace(all=lambda: [])

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.projects.duty.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        resp = await client.get("/projects/1/duty/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.duty.get_project_path",
            AsyncStub(None),
        )
        resp = await client.get("/projects/999/duty/status")
        assert resp.status_code == 404


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):  # noqa: ARG002
        return self._value


@asynccontextmanager
async def _ctx(session):
    yield session
