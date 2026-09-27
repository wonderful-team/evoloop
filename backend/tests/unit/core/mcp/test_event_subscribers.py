"""MCP 生命周期事件（event/subscribers.py）单元测试。

覆盖：APP_STARTED 连接所有、APP_STOPPING 断开、CONFIG_CHANGED 工作区变更重载、
init_mcp DB 初始化、reload_mcp_for_workspace_change。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.mcp.event.subscribers import (
    init_mcp,
    reload_mcp_for_workspace_change,
)


class TestInitMcp:
    async def test_existing_servers_skipped(self):
        db_session = _db_session(all_rows=[("github",)])
        with patch(
            "app.core.mcp.event.subscribers.session_scope",
            _fake_session_scope(db_session),
        ):
            results = await init_mcp()
        assert results == {"github": "skipped_existing"}

    async def test_no_servers(self):
        db_session = _db_session(all_rows=[])
        with patch(
            "app.core.mcp.event.subscribers.session_scope",
            _fake_session_scope(db_session),
        ):
            results = await init_mcp()
        assert results == {}


class TestAppLifecycle:
    async def test_on_application_started(self):
        from app.core.mcp.event.subscribers import McpLifecycleSubscriber

        sub = McpLifecycleSubscriber()
        event = SimpleNamespace()
        with (
            patch("app.core.mcp.event.subscribers.init_mcp", new=AsyncMock(return_value={"a": "ok"})),
            patch("app.core.mcp.client.manager.mcp_client_manager.connect_all") as connect_all,
        ):
            connect_all.return_value = [SimpleNamespace(success=True)]
            await sub.on_application_started(event)
        connect_all.assert_awaited_once()

    async def test_on_application_stopping(self):
        from app.core.mcp.event.subscribers import McpLifecycleSubscriber

        sub = McpLifecycleSubscriber()
        with patch("app.core.mcp.client.manager.mcp_client_manager.disconnect_all") as disconnect_all:
            disconnect_all.return_value = None
            await sub.on_application_stopping(SimpleNamespace())
        disconnect_all.assert_awaited_once()

    async def test_on_config_changed_workspace(self):
        from app.core.mcp.event.subscribers import McpLifecycleSubscriber

        sub = McpLifecycleSubscriber()
        with (
            patch(
                "app.core.mcp.event.subscribers.reload_mcp_for_workspace_change",
                new=AsyncMock(return_value={"ok": True}),
            ) as reload_mock,
        ):
            await sub.on_config_changed(SimpleNamespace(data={"key": "WORKSPACE_ROOT", "new_value": "/x"}))
        reload_mock.assert_awaited_once()

    async def test_on_config_changed_other_key(self):
        from app.core.mcp.event.subscribers import McpLifecycleSubscriber

        sub = McpLifecycleSubscriber()
        with (
            patch(
                "app.core.mcp.event.subscribers.reload_mcp_for_workspace_change",
                new=AsyncMock(),
            ) as reload_mock,
        ):
            await sub.on_config_changed(SimpleNamespace(data={"key": "OTHER", "new_value": 1}))
        reload_mock.assert_not_awaited()


class TestReloadMcpForWorkspaceChange:
    async def test_reconnect_filesystem(self):
        mgr = MagicMock()
        mgr.sessions = {"filesystem": MagicMock()}
        mgr.remove_server = AsyncMock(return_value=True)
        mgr.ensure_connected = AsyncMock(return_value=True)

        with (
            patch("app.core.mcp.event.subscribers.init_mcp", new=AsyncMock(return_value={})),
            patch("app.core.mcp.mcp_client_manager", mgr),
        ):
            results = await reload_mcp_for_workspace_change()
        assert results["disconnect"] == "success"
        assert results["reconnect"] == "success"
        mgr.remove_server.assert_awaited_once_with("filesystem")

    async def test_filesystem_not_connected(self):
        mgr = MagicMock()
        mgr.sessions = {}
        mgr.ensure_connected = AsyncMock(return_value=True)

        with (
            patch("app.core.mcp.event.subscribers.init_mcp", new=AsyncMock(return_value={})),
            patch("app.core.mcp.mcp_client_manager", mgr),
        ):
            results = await reload_mcp_for_workspace_change()
        assert results["disconnect"] == "not_connected"
        assert results["reconnect"] == "success"


class _FakeScope:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _fake_session_scope(session):
    return lambda: _FakeScope(session)


def _db_session(all_rows):
    """构造 DB session：execute 是 AsyncMock，all()/scalars().all() 返回 all_rows。"""
    session = MagicMock()
    session.execute = AsyncMock()
    result = MagicMock()
    result.all.return_value = all_rows
    result.scalars.return_value.all.return_value = all_rows
    session.execute.return_value = result
    return session
