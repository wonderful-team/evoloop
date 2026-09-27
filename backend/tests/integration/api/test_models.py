"""Integration tests for the /models API routes (app/api/routes/models.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_model_manager(monkeypatch):
    from app.api.routes import models as route_mod

    async def _wait_progress(_model_id):
        yield SimpleNamespace(
            model_id="qwen3_asr", progress=50, status="downloading", error=None
        )

    stub = SimpleNamespace(
        get_status=lambda model_id: {"model_id": model_id, "status": "ready"},
        get_all_status=lambda: [
            {"model_id": "qwen3_asr", "status": "ready"},
            {"model_id": "bge-base-zh-v1.5", "status": "ready"},
        ],
        start_download=_start_download,
        wait_for_progress=_wait_progress,
    )
    monkeypatch.setattr(route_mod, "model_manager", stub)


async def _start_download(_model_id):
    return None


async def test_get_all_model_status(client):
    resp = await client.get("/models/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data


async def test_get_single_model_status(client):
    resp = await client.get("/models/status?model_id=qwen3_asr")
    assert resp.status_code == 200
    assert resp.json()["model_id"] == "qwen3_asr"


async def test_get_unknown_model_status(client, monkeypatch):
    from app.api.routes import models as route_mod

    def _error_status(_model_id):
        return {"error": "not found"}

    monkeypatch.setattr(route_mod.model_manager, "get_status", _error_status)
    resp = await client.get("/models/status?model_id=unknown")
    assert resp.status_code == 404


async def test_start_download_success(client):
    resp = await client.post("/models/download", json={"model_id": "qwen3_asr"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["model_id"] == "qwen3_asr"


async def test_start_download_unknown_model(client):
    resp = await client.post("/models/download", json={"model_id": "nonexistent"})
    assert resp.status_code == 400
    assert "Unknown model_id" in resp.json()["error"]


async def test_start_download_already_downloading(client, monkeypatch):
    from app.api.routes import models as route_mod

    async def _raise_runtime(_model_id):
        raise RuntimeError("already downloading")

    monkeypatch.setattr(route_mod.model_manager, "start_download", _raise_runtime)
    resp = await client.post("/models/download", json={"model_id": "qwen3_asr"})
    assert resp.status_code == 409


async def test_download_progress_stream(client):
    resp = await client.get("/models/download/progress?model_id=qwen3_asr")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
