"""Integration tests for the route init endpoint (app/api/routes/route.py)."""

from __future__ import annotations

import json
from types import SimpleNamespace


async def test_no_cache_returns_pending(client, monkeypatch):
    async def _get(_key):
        return None

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init")
    assert resp.status_code == 202
    data = resp.json()
    assert data["unchanged"] is False
    assert data["version"] == "pending"


async def test_cache_read_error_returns_pending(client, monkeypatch):
    async def _get(_key):
        raise RuntimeError("cache down")

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init")
    assert resp.status_code == 202


async def test_version_match_unchanged(client, monkeypatch):
    spec = {"version": "v2", "routes": []}

    async def _get(_key):
        return json.dumps(spec)

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init?version=v2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["unchanged"] is True
    assert data["version"] == "v2"


async def test_version_mismatch_returns_spec(client, monkeypatch):
    spec = {"version": "v2", "routes": ["/a", "/b"]}

    async def _get(_key):
        return json.dumps(spec)

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init?version=v1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["unchanged"] is False
    assert data["version"] == "v2"
    assert data["routes"] == ["/a", "/b"]


async def test_bad_json_returns_pending(client, monkeypatch):
    async def _get(_key):
        return "not-json"

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init")
    assert resp.status_code == 202
    assert resp.json()["unchanged"] is False


async def test_dict_cache_value(client, monkeypatch):
    spec = {"version": "v3", "routes": []}

    async def _get(_key):
        return spec

    monkeypatch.setattr("app.infrastructure.cache.cache", SimpleNamespace(get=_get))
    resp = await client.get("/route/init?version=v2")
    assert resp.status_code == 200
    assert resp.json()["unchanged"] is False
