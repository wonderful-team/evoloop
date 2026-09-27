"""McpClientManager 核心连接管理单元测试。

覆盖：connect / disconnect / connect_all / connect_from_db / ensure_connected /
健康检查 / add_server / remove_server / list_servers / tools 访问。
通过 mock transport、session 与 DB 隔离网络与存储。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.mcp.client.manager import McpClientManager
from app.core.mcp.config import (
    ConnectionState,
    McpServerConfig,
    TransportType,
)


class _FakeScope:
    """真实 async 上下文管理器，yield 指定 session（避免 AsyncMock 协议混乱）。"""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


_UNSET = object()


def _db_session(servers=_UNSET, first=_UNSET, delete_target=_UNSET):
    """构造 DB session：execute 是 AsyncMock（awaitable），返回的 result 是 MagicMock。

    配置 execute 返回的 scalars().all()/first()，供 connect_from_db/add_server/... 使用。
    """
    session = MagicMock()
    session.execute = AsyncMock()
    result = MagicMock()
    scalars = result.scalars.return_value
    if servers is not _UNSET:
        scalars.all.return_value = servers
    if first is not _UNSET:
        scalars.first.return_value = first
    if delete_target is not _UNSET:
        session.delete = AsyncMock(return_value=delete_target)
    session.execute.return_value = result
    return session


def _fake_session_scope(session=None):
    """构造 mock 的 session_scope：可调用，返回真实 async CM，yield 指定 session。"""
    s = session or _db_session()
    return lambda: _FakeScope(s)


def _server_config(name: str = "github", sse: bool = False) -> McpServerConfig:
    if sse:
        return McpServerConfig(
            name=name, transport=TransportType.SSE, url="https://example.com/mcp"
        )
    return McpServerConfig(name=name, command="npx @github/mcp")


class _Feature:
    """Feature 替身：模拟 tools/resources/prompts feature。"""

    def __init__(self, tools=None, resources=None, prompts=None):
        self._tools = tools or []
        self._resources = resources or []
        self._prompts = prompts or []

    def get_tools(self):
        return self._tools

    def get_resources(self):
        return self._resources

    def get_prompts(self):
        return self._prompts


@pytest.fixture()
def mock_transport():
    """替换 manager._transport，让 connect 走假 session。"""
    session = AsyncMock()
    session.list_tools.return_value = SimpleNamespace(tools=[])
    session.list_resources.return_value = SimpleNamespace(resources=[])
    session.list_prompts.return_value = SimpleNamespace(prompts=[])

    transport = MagicMock()
    transport.create_transport.return_value = _AsyncCM(("r", "w"))
    transport.create_session = AsyncMock(return_value=session)
    return transport, session


class _AsyncCM:
    """最小 async 上下文管理器替身。"""

    def __init__(self, value):
        self._value = value
        self.exited = False

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        self.exited = True
        return False


def _manager_with_features(transport, tools_feature=None, resource_feature=None, prompt_feature=None):
    mgr = McpClientManager()
    mgr._transport = transport
    tools = tools_feature or _Feature()
    resources = resource_feature or _Feature()
    prompts = prompt_feature or _Feature()
    return mgr, tools, resources, prompts


class TestConnect:
    async def test_connect_success(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        result = await mgr.connect(_server_config())
        assert result.success is True
        assert result.server_name == "github"
        assert "github" in mgr._tools_feature

    async def test_connect_publishes_notification_handler(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config())
        # create_session 收到 message_handler
        assert transport.create_session.await_args.kwargs.get("message_handler") is not None
        assert "github" in mgr._sessions
        assert "github" in mgr._configs

    async def test_connect_failure_returns_result(self, mock_transport):
        transport, session = mock_transport
        transport.create_transport.side_effect = RuntimeError("connect failed")
        mgr = McpClientManager()
        mgr._transport = transport
        result = await mgr.connect(_server_config())
        assert result.success is False
        assert "connect failed" in (result.error or "")

    async def test_connect_disconnects_existing(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config())
        mgr.disconnect = AsyncMock()
        await mgr.connect(_server_config())
        mgr.disconnect.assert_awaited_once_with("github")


class TestDisconnect:
    async def test_disconnect_cleans_state(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config())
        mgr._tools_feature["github"] = _Feature()
        mgr._resources_feature["github"] = _Feature()
        mgr._prompts_feature["github"] = _Feature()

        await mgr.disconnect("github")
        assert "github" not in mgr._sessions
        # _configs 故意保留：重连（ensure_connected/_ensure_alive_force）依赖缓存配置
        assert "github" in mgr._configs
        assert "github" not in mgr._tools_feature
        assert "github" not in mgr._resources_feature
        assert "github" not in mgr._prompts_feature

    async def test_disconnect_unknown_server_is_noop(self, mock_transport):
        mgr = McpClientManager()
        await mgr.disconnect("nonexistent")  # 不应抛错


class TestConnectFromDb:
    async def test_connect_from_db_sse(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        db_server = SimpleNamespace(
            name="mall",
            command="https://example.com/mcp",
            args=None,
            env=None,
            enabled=True,
        )
        db_session = _db_session(first=db_server)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            result = await mgr.connect_from_db("mall")
        assert result.success is True
        assert result.server_name == "mall"

    async def test_connect_from_db_missing_server(self, mock_transport):
        mgr = McpClientManager()
        db_session = _db_session(first=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            result = await mgr.connect_from_db("nope")
        assert result.success is False
        assert "not found" in (result.error or "")


class TestEnsureConnected:
    async def test_reconnects_when_stale(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config())
        # 健康检查失败 → 触发重连
        mgr._health_checker = MagicMock()
        mgr._health_checker.check = AsyncMock(return_value=SimpleNamespace(is_healthy=False))
        db_server = SimpleNamespace(
            name="github", command="npx @github/mcp", args=None, env=None, enabled=True
        )
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(_db_session(first=db_server)),
        ):
            ok = await mgr.ensure_connected("github")
        assert ok is True  # 已重连

    async def test_ensure_connected_unknown_server(self, mock_transport):
        mgr = McpClientManager()
        db_session = _db_session(first=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            ok = await mgr.ensure_connected("nope")
        assert ok is False


class TestGetTools:
    async def test_get_tools_all_servers(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config("github"))
        tool = MagicMock()
        mgr._tools_feature["github"] = _Feature(tools=[tool])
        tools = await mgr.get_tools()
        assert tools == [tool]

    async def test_get_tools_specific_server(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config("github"))
        tool = MagicMock()
        mgr._tools_feature["github"] = _Feature(tools=[tool])
        tools = await mgr.get_tools("github")
        assert tools == [tool]


class TestServerManagement:
    async def test_add_server_creates_and_connects(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        db_session = _db_session(first=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            result = await mgr.add_server(
                "new-srv", {"command": "npx foo", "args": [], "env": {}, "enabled": True}
            )
        assert result.success is True
        assert result.server_name == "new-srv"

    async def test_add_server_disabled_stores_only(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        mgr.disconnect = AsyncMock()
        db_session = _db_session(first=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            result = await mgr.add_server(
                "off", {"command": "npx foo", "enabled": False}
            )
        assert result.success is True
        assert result.tools_count == 0
        mgr.disconnect.assert_awaited_once_with("off")

    async def test_remove_server(self, mock_transport):
        mgr = McpClientManager()
        mgr.disconnect = AsyncMock()
        db_session = _db_session(first=SimpleNamespace(), delete_target=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            ok = await mgr.remove_server("srv")
        assert ok is True

    async def test_remove_server_not_found(self, mock_transport):
        mgr = McpClientManager()
        mgr.disconnect = AsyncMock()
        db_session = _db_session(first=None)
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            ok = await mgr.remove_server("srv")
        assert ok is False

    async def test_list_servers(self, mock_transport):
        mgr = McpClientManager()
        db_server = SimpleNamespace(
            name="github", command="npx foo", enabled=True, transport=None
        )
        db_session = _db_session(servers=[db_server])
        with patch(
            "app.core.mcp.client.manager.session_scope",
            _fake_session_scope(db_session),
        ):
            servers = await mgr.list_servers()
        assert len(servers) == 1
        assert servers[0].name == "github"
        assert servers[0].status in ("connected", "available")


class TestNotificationHandler:
    async def test_publishes_generic_event(self):
        mgr = McpClientManager()
        handler = mgr._build_message_handler("capability-matrix")
        published = []
        done = asyncio.Event()

        async def fake_publish(event):
            published.append(event)
            done.set()

        with patch(
            "app.core.mcp.client.manager.system_bus",
            SimpleNamespace(publish=fake_publish),
        ):
            await handler(SimpleNamespace(root=SimpleNamespace(
                method="notifications/mcp_message", params={"count": 1}
            )))
            # 派发走后台任务（不阻塞接收循环），等它完成再断言
            await asyncio.wait_for(done.wait(), timeout=1)
        assert len(published) == 1
        ev = published[0]
        assert ev.method == "notifications/mcp_message"
        assert ev.server_name == "capability-matrix"
        assert ev.data.method == "notifications/mcp_message"
        assert ev.data.payload == {"count": 1}

    async def test_ignores_non_notification(self):
        mgr = McpClientManager()
        handler = mgr._build_message_handler("srv")
        published = []

        async def fake_publish(event):
            published.append(event)

        with patch(
            "app.core.mcp.client.manager.system_bus",
            SimpleNamespace(publish=fake_publish),
        ):
            await handler(SimpleNamespace(root=SimpleNamespace(method="tools/call")))
        assert published == []


class TestGetConnectionState:
    async def test_state(self, mock_transport):
        transport, session = mock_transport
        mgr = McpClientManager()
        mgr._transport = transport
        await mgr.connect(_server_config("github"))
        st = mgr.get_connection_state("github")
        assert isinstance(st, ConnectionState)
        assert st.server_name == "github"
