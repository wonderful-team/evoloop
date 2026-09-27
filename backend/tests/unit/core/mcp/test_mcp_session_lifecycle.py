"""MCP 会话生命周期单元测试。

覆盖本次修复：keepalive 保活、ensure_alive 失联重连、工具调用走活会话、
超时兜底由 McpMessageChannel 测试覆盖。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.mcp.client.manager import McpClientManager
from app.core.mcp.features.tools import McpToolsFeature
from app.core.mcp.transport import McpTransport


def _tool(name="t1", input_schema=None):
    return SimpleNamespace(
        name=name,
        description="desc",
        inputSchema=input_schema or {"type": "object", "properties": {}},
    )


class TestMcpCreateSessionCleanup:
    async def test_initialize_timeout_exits_session_before_propagating(self) -> None:
        """initialize 超时（被 wait_for 取消）时，create_session 必须先把
        session 的 receive-loop task group 退出（弹出 cancel scope），
        否则外层 transport 的 __aexit__ 会报 "Attempted to exit a cancel scope..."。"""
        fake = AsyncMock()
        fake.__aenter__ = AsyncMock(return_value=fake)
        fake.initialize = AsyncMock(side_effect=asyncio.TimeoutError())
        fake.__aexit__ = AsyncMock(return_value=None)
        read, write = AsyncMock(), AsyncMock()
        with (
            patch("app.core.mcp.transport._patch_receive_notification_type"),
            patch("app.core.mcp.transport.ClientSession", return_value=fake),
        ):
            with pytest.raises(asyncio.TimeoutError):
                await McpTransport.create_session(read, write, timeout=1)
        fake.__aexit__.assert_awaited_once()

    async def test_initialize_ok_does_not_exit_session(self) -> None:
        fake = AsyncMock()
        fake.__aenter__ = AsyncMock(return_value=fake)
        fake.initialize = AsyncMock(return_value=SimpleNamespace(protocolVersion="2025-03-26"))
        fake.__aexit__ = AsyncMock(return_value=None)
        read, write = AsyncMock(), AsyncMock()
        with (
            patch("app.core.mcp.transport._patch_receive_notification_type"),
            patch("app.core.mcp.transport.ClientSession", return_value=fake),
        ):
            out = await McpTransport.create_session(read, write, timeout=1)
        assert out is fake
        fake.__aexit__.assert_not_awaited()


class TestMcpToolsFeatureEnsureAlive:
    async def test_tool_func_uses_live_session_via_hook(self) -> None:
        """工具调用前先走 ensure_alive 钩子，用返回的活会话调用。"""
        session1 = AsyncMock()
        session1.list_tools.return_value = SimpleNamespace(tools=[_tool()])
        session1.call_tool = AsyncMock(return_value="result")

        session2 = AsyncMock()  # 重连后的活会话
        session2.call_tool = AsyncMock(return_value="result2")

        async def ensure_alive(server_name):
            assert server_name == "mall"
            return session2

        feat = McpToolsFeature()
        await feat.initialize(session1, "mall", ensure_alive=ensure_alive)
        tool = feat.get_tools()[0]
        out = await tool.func(a=1)
        # 用的是 session2（活会话），且钩子被调用
        session2.call_tool.assert_awaited_once_with("t1", arguments={"a": 1})
        session1.call_tool.assert_not_awaited()
        assert out == "result2"

    async def test_tool_func_no_hook_uses_own_session(self) -> None:
        session = AsyncMock()
        session.list_tools.return_value = SimpleNamespace(tools=[_tool()])
        session.call_tool = AsyncMock(return_value="r")
        feat = McpToolsFeature()
        await feat.initialize(session, "mall")
        tool = feat.get_tools()[0]
        assert await tool.func(x=2) == "r"
        session.call_tool.assert_awaited_once_with("t1", arguments={"x": 2})

    async def test_tool_func_raises_when_session_unavailable(self) -> None:
        session = AsyncMock()
        session.list_tools.return_value = SimpleNamespace(tools=[_tool()])
        feat = McpToolsFeature()
        await feat.initialize(session, "mall", ensure_alive=AsyncMock(return_value=None))
        tool = feat.get_tools()[0]
        with pytest.raises(RuntimeError, match="不可用"):
            await tool.func()

    async def test_tool_func_call_failure_forces_reconnect_and_retry(self) -> None:
        """call_tool 失败（ping 通但会话退化）→ 强制重连 + 重试一次。"""
        dead = AsyncMock()
        dead.list_tools.return_value = SimpleNamespace(tools=[_tool()])
        dead.call_tool = AsyncMock(side_effect=RuntimeError("Connection closed"))

        fresh = AsyncMock()
        fresh.call_tool = AsyncMock(return_value="ok")

        force_calls = []

        async def ensure_alive(server_name):
            return dead  # ping "通"，返回退化会话

        async def ensure_alive_force(server_name):
            force_calls.append(server_name)
            return fresh

        feat = McpToolsFeature()
        await feat.initialize(dead, "mall", ensure_alive=ensure_alive, ensure_alive_force=ensure_alive_force)
        tool = feat.get_tools()[0]
        out = await tool.func(a=1)
        # 第一次 call 失败 → 强制重连 → 在新会话重试成功
        assert out == "ok"
        assert force_calls == ["mall"]
        fresh.call_tool.assert_awaited_once_with("t1", arguments={"a": 1})


class TestMcpHealthCheckTimeout:
    async def test_health_check_times_out_on_degraded_session(self) -> None:
        """退化会话上 list_tools 挂起 → 健康检查必须在 timeout 内返回不健康，
        不能永久阻塞调用方（否则推送轮巡会被拖死，占用全局轮巡锁）。"""
        from app.core.mcp.health import McpHealthChecker

        checker = McpHealthChecker(timeout_seconds=0.1)

        async def hang():
            await asyncio.Event().wait()

        session = AsyncMock()
        session.list_tools = hang
        status = await checker.check("mall", session)
        assert status.is_healthy is False
        assert status.response_time_ms < 1000  # 在 timeout 内返回，未永久挂起


class TestMcpNotificationDispatchNonBlocking:
    async def test_notification_handler_returns_immediately_not_blocking(self) -> None:
        """推送通知的 message_handler 必须立即返回（后台派发）。

        否则接收循环被订阅方阻塞：推送后的轮巡调 MCP 工具（mcp_messages_list）时，工具
        响应需要接收循环投递 → 互等死锁 → ping 响应也处理不了 → 被判死重连。
        """
        mgr = McpClientManager()
        handler = mgr._build_message_handler("mall")
        started = asyncio.Event()
        ready = asyncio.Event()

        async def controlled_publish(*a, **k):
            started.set()
            await ready.wait()

        with patch(
            "app.core.mcp.client.manager.system_bus.publish",
            side_effect=controlled_publish,
        ) as mock_pub:
            msg = SimpleNamespace(
                root={"method": "notifications/kf_new_message", "params": {"count": 1}}
            )
            # 1s 内必须返回：若 handler 内 await publish，publish 永不返回 → 超时
            await asyncio.wait_for(handler(msg), timeout=1)
            await asyncio.sleep(0.05)
            assert started.is_set()  # 派发确实被调度为后台任务
            ready.set()  # 释放后台任务
            await asyncio.sleep(0.01)
        mock_pub.assert_called_once()


class _AsyncCM:
    """最小 async 上下文管理器替身（同 test_manager）。"""

    def __init__(self, value):
        self._value = value
        self.exited = False

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        self.exited = True
        return False


class TestManagerKeepaliveAndReconnect:
    def _manager(self) -> McpClientManager:
        m = McpClientManager()
        m._configs = {}
        return m

    def _mock_transport_for(self, session):
        """完整 mock transport：create_transport/create_session 都走假对象。"""
        transport = MagicMock()
        transport.create_transport.return_value = _AsyncCM(("r", "w"))
        transport.create_session = AsyncMock(return_value=session)
        return transport

    async def _run_runner(self, m, session, ping_error=None):
        """spawn _server_runner（mock transport + features），返回 (runner, ready)。"""
        session.send_ping = (
            AsyncMock(side_effect=ping_error) if ping_error else AsyncMock(return_value=None)
        )
        m._transport = self._mock_transport_for(session)
        m.MCP_KEEPALIVE_INTERVAL = 0.02
        m.MCP_PING_TIMEOUT = 0.1

        features = []
        for cls_path in (
            "app.core.mcp.features.tools.McpToolsFeature",
            "app.core.mcp.features.resources.McpResourcesFeature",
            "app.core.mcp.features.prompts.McpPromptsFeature",
        ):
            patcher = patch(cls_path)
            cls_mock = patcher.start()
            inst = cls_mock.return_value
            inst.initialize = AsyncMock()
            if "tools" in cls_path:
                inst.get_tools.return_value = []
            features.append(patcher)
        ready = asyncio.Event()
        runner = asyncio.create_task(m._server_runner("mall", MagicMock(), ready))
        return runner, ready, features

    async def test_runner_ping_ok_keeps_session(self) -> None:
        """runner：保活 ping 正常 → 会话注册且 runner 常驻，cancel 后清理。"""
        m = self._manager()
        session = AsyncMock()
        runner, ready, patches = await self._run_runner(m, session)
        try:
            await asyncio.wait_for(ready.wait(), timeout=2)
            await asyncio.sleep(0.06)
            assert m._sessions.get("mall") is session
        finally:
            for p_ in patches:
                p_.stop()
        runner.cancel()
        with __import__("contextlib").suppress(BaseException):
            await runner
        assert m._sessions.get("mall") is None

    async def test_runner_ping_death_exits_and_clears(self) -> None:
        """runner：保活 ping 失败 → 自行退出并清理会话注册。"""
        m = self._manager()
        session = AsyncMock()
        runner, ready, patches = await self._run_runner(
            m, session, ping_error=RuntimeError("dead")
        )
        try:
            await asyncio.wait_for(ready.wait(), timeout=2)
            await asyncio.wait_for(runner, timeout=2)
            assert m._sessions.get("mall") is None
        finally:
            for p_ in patches:
                p_.stop()

    async def test_ensure_alive_returns_live_session(self) -> None:
        m = self._manager()
        session = AsyncMock()
        session.send_ping = AsyncMock(return_value=None)
        m._sessions["mall"] = session
        got = await m._ensure_session_alive("mall")
        assert got is session
        session.send_ping.assert_awaited_once()

    async def test_ensure_alive_reconnects_dead_session(self) -> None:
        """会话失联（ping 失败）→ 先断开死会话，再 ensure_connected 重连（锁内串行）。"""
        m = self._manager()
        dead = AsyncMock()
        dead.send_ping = AsyncMock(side_effect=RuntimeError("dead"))
        m._sessions["mall"] = dead
        m._configs["mall"] = MagicMock()  # 缓存 config 供 ensure_connected 重连

        new_session = AsyncMock()
        new_session.send_ping = AsyncMock(return_value=None)

        with (
            patch.object(m, "disconnect", new=AsyncMock()) as mock_disc,
            patch.object(m, "ensure_connected", new=AsyncMock()) as mock_ec,
        ):
            def _set(*a, **k):
                m._sessions["mall"] = new_session
                return True

            mock_ec.side_effect = _set

            got = await m._ensure_session_alive("mall")

        assert got is new_session
        mock_disc.assert_awaited_once()
        mock_ec.assert_awaited_once()

    async def test_ensure_alive_missing_session_reconnects(self) -> None:
        m = self._manager()
        m._sessions = {}
        new_session = AsyncMock()

        with patch.object(m, "ensure_connected", new=AsyncMock()) as mock_ec:
            def _set(*a, **k):
                m._sessions["mall"] = new_session
                return True

            mock_ec.side_effect = _set
            got = await m._ensure_session_alive("mall")
        assert got is new_session
