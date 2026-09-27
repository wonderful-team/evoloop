"""Integration tests for the /utils API routes (app/api/routes/utils.py)."""

from __future__ import annotations

from types import SimpleNamespace


async def test_health_check(client):
    resp = await client.get("/utils/health-check/")
    assert resp.status_code == 200
    assert resp.json() is True


async def test_ai_config(client):
    resp = await client.get("/utils/ai/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "models" in data["data"]
    assert "limits" in data["data"]


class TestEvoloopStatus:
    async def test_connected(self, client, monkeypatch):

        mock_link = SimpleNamespace(
            is_connected=lambda: True,
            device_key="dk-123",
            device_name="Test Device",
        )

        class FakeManager:
            link = mock_link

        monkeypatch.setattr(
            "app.api.routes.utils.evocloud_manager",
            FakeManager(),
        )
        resp = await client.get("/utils/evoloop-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["device_key"] == "dk-123"
        assert data["device_name"] == "Test Device"

    async def test_disconnected(self, client, monkeypatch):
        class FakeManager:
            link = None

        monkeypatch.setattr(
            "app.api.routes.utils.evocloud_manager",
            FakeManager(),
        )
        resp = await client.get("/utils/evoloop-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["device_key"] is None
        assert data["device_name"] == "Unknown"
