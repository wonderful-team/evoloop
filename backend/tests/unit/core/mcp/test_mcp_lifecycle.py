"""Unit tests for McpLifecycleSubscriber lifecycle contract.

Guards the APP_STARTED connection behavior (so MCP servers are connected
exactly once at startup — see the removed duplicate in app/main.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.mcp.event.subscribers import McpLifecycleSubscriber


async def test_app_started_initializes_and_connects():
    with (
        patch(
            "app.core.mcp.event.subscribers.init_mcp",
            new=AsyncMock(return_value={"local": "ok"}),
        ),
        patch(
            "app.core.mcp.client.manager.McpClientManager.connect_all",
            new=AsyncMock(return_value=[]),
        ) as connect_all,
    ):
        await McpLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))

    connect_all.assert_awaited_once()


async def test_app_stopping_disconnects():
    with patch(
        "app.core.mcp.client.manager.McpClientManager.disconnect_all",
        new=AsyncMock(),
    ) as disconnect:
        await McpLifecycleSubscriber().on_application_stopping(SimpleNamespace(data={}))
        disconnect.assert_awaited_once()
