"""Integration tests for generation API endpoints using real login token."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.projects import generations_router
from app.core.evocloud import evocloud_manager
from app.domain.codebase.generation.scheduler import scheduler


@pytest.fixture(scope="module")
async def auth_token():
    """Login once per module and return a real access token."""
    evocloud_manager.initialize()
    login_res = await evocloud_manager.login("preterchan", "hellomylife")
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")
    return login_res["token"]


@pytest.fixture
async def client(tmp_path, auth_token):
    """Create an async HTTP client over the generations router with a real login token."""
    scheduler._base_dir = tmp_path
    scheduler._tasks.clear()
    scheduler._locks.clear()

    app = FastAPI()
    app.include_router(generations_router, prefix="/api/v1/projects")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as ac:
        yield ac

    await scheduler.drain()
    scheduler._tasks.clear()


class TestGenerationDispatch:
    async def test_dispatch_known_items(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki", "appmap"]},
        )
        await scheduler.drain()
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == 1
        assert "wiki" in data["dispatched"]
        assert "appmap" in data["dispatched"]

        status_resp = await client.get("/api/v1/projects/1/generations")
        items = {r["item"]: r for r in status_resp.json()["items"]}
        assert items["wiki"]["status"] == "completed"
        assert items["appmap"]["status"] == "completed"

    async def test_dispatch_unknown_item_ignored(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["unknown", "wiki"]},
        )
        await scheduler.drain()
        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == ["wiki"]
        assert "unknown" not in data["items"]

    async def test_dispatch_overview_ignored(self, client):
        """overview is no longer handled by GenerationScheduler."""
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["overview"]},
        )
        await scheduler.drain()
        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == []
        assert "overview" not in data["items"]

    async def test_dispatch_project_id_mismatch(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 2, "items": ["wiki"]},
        )
        assert resp.status_code == 400

    async def test_dispatch_empty_items(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": []},
        )
        await scheduler.drain()
        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == []

    async def test_dispatch_while_running_does_not_redispatch(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        data = resp.json()
        assert data["dispatched"] == []


class TestGenerationStatus:
    async def test_list_status(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        await scheduler.drain()
        resp = await client.get("/api/v1/projects/1/generations")
        assert resp.status_code == 200
        data = resp.json()
        items = {r["item"]: r for r in data["items"]}
        assert set(items.keys()) == {"wiki", "appmap", "summary"}
        assert items["wiki"]["status"] == "completed"


class TestGenerationRetry:
    async def test_retry_failed_item(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        await scheduler.drain()
        record = scheduler._ensure_record(scheduler._load(1), "wiki")
        scheduler._update_record(record, "failed", error="timeout")
        scheduler._save(scheduler._load(1))

        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "wiki"},
        )
        await scheduler.drain()
        assert resp.status_code == 200

        status_resp = await client.get("/api/v1/projects/1/generations")
        items = {r["item"]: r for r in status_resp.json()["items"]}
        assert items["wiki"]["status"] == "completed"

    async def test_retry_unknown_item(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations/unknown/retry",
            json={"project_id": 1, "item": "unknown"},
        )
        assert resp.status_code == 400

    async def test_retry_project_id_mismatch(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 2, "item": "wiki"},
        )
        assert resp.status_code == 400

    async def test_retry_item_mismatch(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "appmap"},
        )
        assert resp.status_code == 400

    async def test_retry_running_item(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "wiki"},
        )
        assert resp.status_code == 200
        data = resp.json()
        items = {r["item"]: r for r in data["items"]}
        assert items["wiki"]["status"] == "running"

    async def test_retry_non_failed_item(self, client):
        """Retrying a completed item re-runs it."""
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        await scheduler.drain()
        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 1, "item": "wiki"},
        )
        await scheduler.drain()
        assert resp.status_code == 200


class TestGenerationContent:
    async def test_get_content_completed(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["summary"]},
        )
        await scheduler.drain()
        resp = await client.get("/api/v1/projects/1/generations/summary/content")
        assert resp.status_code == 200
        data = resp.json()
        assert data["item"] == "summary"
        assert data["content_type"] == "markdown"
        assert "project 1" in (data["content"] or "")

    async def test_get_content_appmap_json(self, client):
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["appmap"]},
        )
        await scheduler.drain()
        resp = await client.get("/api/v1/projects/1/generations/appmap/content")
        data = resp.json()
        assert data["content_type"] == "json"
        assert '"routes"' in (data["content"] or "")

    async def test_get_content_unknown_item(self, client):
        resp = await client.get("/api/v1/projects/1/generations/unknown/content")
        assert resp.status_code == 400

    async def test_get_content_pending_item(self, client):
        """Content endpoint returns null for an item that was never dispatched."""
        resp = await client.get("/api/v1/projects/1/generations/wiki/content")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] is None


class TestGenerationEdgeCases:
    async def test_concurrent_dispatches_same_project(self, client):
        """Two rapid dispatches should not corrupt the status store."""
        resp1 = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        resp2 = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["appmap"]},
        )
        await scheduler.drain()
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        status_resp = await client.get("/api/v1/projects/1/generations")
        items = {r["item"]: r for r in status_resp.json()["items"]}
        assert items["wiki"]["status"] == "completed"
        assert items["appmap"]["status"] == "completed"

    async def test_isolated_status_per_project(self, client):
        """Status files for different projects should not leak."""
        await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1, "items": ["wiki"]},
        )
        await client.post(
            "/api/v1/projects/2/generations",
            json={"project_id": 2, "items": ["appmap"]},
        )
        await scheduler.drain()

        resp1 = await client.get("/api/v1/projects/1/generations")
        resp2 = await client.get("/api/v1/projects/2/generations")
        items1 = {r["item"]: r for r in resp1.json()["items"]}
        items2 = {r["item"]: r for r in resp2.json()["items"]}
        assert items1["wiki"]["status"] == "completed"
        assert items2["appmap"]["status"] == "completed"
        assert items1.get("appmap", {}).get("status") != "completed"
        assert items2.get("wiki", {}).get("status") != "completed"

    async def test_dispatch_invalid_payload(self, client):
        """Missing required fields should yield a validation error."""
        resp = await client.post(
            "/api/v1/projects/1/generations",
            json={"project_id": 1},
        )
        assert resp.status_code == 422

    async def test_retry_invalid_payload(self, client):
        resp = await client.post(
            "/api/v1/projects/1/generations/wiki/retry",
            json={"project_id": 1},
        )
        assert resp.status_code == 422

    async def test_unauthorized_request(self, client):
        """Requests without a valid Authorization header are rejected."""
        client.headers.pop("Authorization", None)
        resp = await client.get("/api/v1/projects/1/generations")
        assert resp.status_code == 401
