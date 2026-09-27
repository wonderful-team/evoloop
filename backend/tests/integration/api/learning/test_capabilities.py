"""Integration tests for the /capabilities API routes (app/api/routes/learning/capabilities.py)."""

from __future__ import annotations

from types import SimpleNamespace


async def test_list_actions(client, monkeypatch):
    monkeypatch.setattr(
        "app.core.environment.capabilities.registry.ActionRegistry.list_actions",
        lambda platform=None: [
            SimpleNamespace(
                id="click",
                platforms=["dom", "mobile"],
                icon="mouse-pointer",
                description="Click action",
                translation_key="actions.click",
                params={},
                mappings={"mobile": "tap"},
            )
        ],
    )
    resp = await client.get("/learning/capabilities/actions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "click"


async def test_list_actions_empty(client, monkeypatch):
    monkeypatch.setattr(
        "app.core.environment.capabilities.registry.ActionRegistry.list_actions",
        lambda platform=None: [],
    )
    resp = await client.get("/learning/capabilities/actions")
    assert resp.status_code == 200
    assert resp.json() == []
