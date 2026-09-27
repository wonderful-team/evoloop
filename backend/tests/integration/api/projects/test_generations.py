"""Integration tests for projects/generations.py routes."""

from __future__ import annotations

import pytest  # noqa: F401


@pytest.fixture(autouse=True)
def _mock_check_benefit(monkeypatch):
    monkeypatch.setattr("app.api.deps.check_benefit", AsyncStub(True))


class TestDispatchGeneration:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.dispatch_generation",
            AsyncStub(
                {
                    "dispatched": ["wiki"],
                    "items": {"wiki": {"item": "wiki", "status": "pending"}},
                }
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.generations.run_generation_item", lambda *a: None
        )
        resp = await client.post(
            "/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == 1
        assert "wiki" in data["dispatched"]

    async def test_project_id_mismatch(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.dispatch_generation",
            AsyncStub({"dispatched": [], "items": {}}),
        )
        resp = await client.post(
            "/projects/1/generations",
            json={"project_id": 2, "items": ["wiki"]},
        )
        assert resp.status_code == 400

    async def test_empty_dispatch(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.dispatch_generation",
            AsyncStub({"dispatched": [], "items": {}}),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.generations.run_generation_item", lambda *a: None
        )
        resp = await client.post(
            "/projects/1/generations",
            json={"project_id": 1, "items": []},
        )
        assert resp.status_code == 200
        assert resp.json()["dispatched"] == []


class TestListGenerationStatus:
    async def test_empty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.list_generation_status",
            AsyncStub([]),
        )
        resp = await client.get("/projects/1/generations")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_with_records(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.list_generation_status",
            AsyncStub(
                [
                    {"item": "wiki", "status": "completed"},
                    {"item": "appmap", "status": "pending"},
                ]
            ),
        )
        resp = await client.get("/projects/1/generations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["item"] == "wiki"


class TestRetryGeneration:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.retry_generation_item",
            AsyncStub({"status": "pending"}),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.generations.list_generation_status",
            AsyncStub([{"item": "wiki", "status": "pending"}]),
        )
        resp = await client.post(
            "/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "wiki"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"][0]["status"] == "pending"

    async def test_mismatch(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.retry_generation_item",
            AsyncStub({"status": "pending"}),
        )
        resp = await client.post(
            "/projects/1/generations/wiki/retry",
            json={"project_id": 2, "item": "wiki"},
        )
        assert resp.status_code == 400

    async def test_scheduler_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.retry_generation_item",
            AsyncStub({"error": "no previous run"}),
        )
        resp = await client.post(
            "/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "wiki"},
        )
        assert resp.status_code == 400


class TestGetGenerationContent:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.get_generation_content",
            AsyncStub({"content": "# Project Wiki", "content_type": "markdown"}),
        )
        resp = await client.get("/projects/1/generations/wiki/content")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "# Project Wiki"
        assert data["item"] == "wiki"

    async def test_unknown_item(self, client, monkeypatch):
        resp = await client.get("/projects/1/generations/nonexistent/content")
        assert resp.status_code == 400

    async def test_no_content(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.generations.get_generation_content",
            AsyncStub({"content": None, "content_type": "markdown"}),
        )
        resp = await client.get("/projects/1/generations/wiki/content")
        assert resp.status_code == 200
        assert resp.json()["content"] is None


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):
        return self._value
