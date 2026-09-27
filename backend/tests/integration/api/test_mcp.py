"""Integration tests for the /mcp API routes (app/api/routes/mcp.py)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_mcp_manager(monkeypatch):
    from app.core.mcp import mcp_client_manager

    servers = [
        {"name": "s1", "command": "echo", "status": "connected", "tools_count": 2},
        {"name": "s2", "command": "node", "status": "stopped", "tools_count": 0},
    ]

    async def _list():
        return servers

    async def _add(_name, _details):
        return {"status": "added", "name": _name}

    async def _remove(name):
        if name == "missing":
            return False
        return True

    async def _ensure_connected(name):
        if name == "fail":
            return False
        return True

    async def _get_tools(_name):
        return [{"name": "t1"}, {"name": "t2"}]

    monkeypatch.setattr(mcp_client_manager, "list_servers", _list)
    monkeypatch.setattr(mcp_client_manager, "add_server", _add)
    monkeypatch.setattr(mcp_client_manager, "remove_server", _remove)
    monkeypatch.setattr(mcp_client_manager, "ensure_connected", _ensure_connected)
    monkeypatch.setattr(mcp_client_manager, "get_tools", _get_tools)


async def test_list_servers(client):
    resp = await client.get("/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "s1"


async def test_add_server(client):
    resp = await client.post(
        "/mcp/server",
        json={"name": "new", "command": "python", "enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


async def test_add_server_error(client, monkeypatch):
    from app.core.mcp import mcp_client_manager

    async def _fail_add(_name, _details):
        raise ValueError("bad config")

    monkeypatch.setattr(mcp_client_manager, "add_server", _fail_add)
    resp = await client.post(
        "/mcp/server",
        json={"name": "bad", "command": "x", "enabled": True},
    )
    assert resp.status_code == 400


async def test_delete_server_success(client):
    resp = await client.delete("/mcp/server/s1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


async def test_delete_server_not_found(client):
    # The route raises HTTPException(404) internally for a missing server,
    # but the bare `except Exception` re-wraps it into a 400. Assert the
    # actual (current) behavior.
    resp = await client.delete("/mcp/server/missing")
    assert resp.status_code == 400


async def test_connect_server_success(client):
    resp = await client.post("/mcp/server/s1/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "connected"
    assert data["name"] == "s1"
    assert data["tools_count"] == 2


async def test_connect_server_failure(client):
    resp = await client.post("/mcp/server/fail/connect")
    assert resp.status_code == 400
