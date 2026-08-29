"""MCP Client Manager - manages connections to external MCP servers."""

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from sqlalchemy import select

from app.core.events.base import BaseEvent, EventData, system_bus
from app.core.events.registry import SystemEventType
from app.core.mcp.auth.manager import mcp_auth_manager
from app.core.mcp.config import (
    AuthType,
    ConnectionResult,
    ConnectionState,
    McpServerConfig,
    TransportType,
    is_sse_url,
)
from app.core.mcp.features.prompts import McpPromptsFeature
from app.core.mcp.features.resources import McpResourcesFeature
from app.core.mcp.features.tools import McpToolsFeature
from app.core.mcp.health import HealthStatus, McpHealthChecker
from app.core.mcp.schemas import (
    McpPrompt,
    McpPromptArgument,
    McpPromptResult,
    McpResource,
    McpResourceContent,
    McpServerSummary,
)
from app.core.mcp.transport import McpTransport
from app.core.tools.base import EvoLoopTool
from app.infrastructure.database import session_scope
from app.models import McpServer

logger = logging.getLogger(__name__)


class McpClientManager:
    """
    Manages connections to external MCP servers and exposes their capabilities.

    Responsibilities:
    - Connection lifecycle management (connect/disconnect/reconnect)
    - Health checking and auto-reconnection
    - Tool caching and conversion
    - Configuration persistence (DB integration)

    A hanging or unresponsive MCP server must NEVER block the core service:
    every connection is bounded by ``MCP_CONNECT_TIMEOUT``.

    Architecture:
        ┌─────────────────────────────────┐
        │      McpClientManager           │
        ├─────────────────────────────────┤
        │  ┌──────────┐  ┌─────────────┐ │
        │  │ Transport│  │HealthChecker│ │
        │  └──────────┘  └─────────────┘ │
        ├─────────────────────────────────┤
        │  ┌────────────────────────────┐ │
        │  │     Features (Tools)       │ │
        │  └────────────────────────────┘ │
        └─────────────────────────────────┘
    """
    MCP_CONNECT_TIMEOUT = 20.0
    MCP_KEEPALIVE_INTERVAL = 10.0
    MCP_PING_TIMEOUT = 5.0

    def __init__(self):
        # Connection state
        self._sessions: dict[str, Any] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._configs: dict[str, McpServerConfig] = {}

        # Features
        self._tools_feature: dict[str, McpToolsFeature] = {}
        self._resources_feature: dict[str, McpResourcesFeature] = {}
        self._prompts_feature: dict[str, McpPromptsFeature] = {}

        # 每 server 一把重连锁：防 keepalive/ensure_alive/调用路径并发重连竞争。
        self._reconnect_locks: dict[str, asyncio.Lock] = {}

        # Sub-components
        self._transport = McpTransport()
        self._health_checker = McpHealthChecker()

        # Legacy migration
        self._legacy_config_path = "mcp_servers_config.json"

    # ═══════════════════════════════════════════════════════════
    # Connection Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def connect(self, config: McpServerConfig) -> ConnectionResult:
        """
        Connect to an MCP server.

        Args:
            config: Server configuration

        Returns:
            ConnectionResult with success status and tool count
        """
        config.validate()
        server_name = config.name

        # Disconnect existing if any
        if server_name in self._stacks:
            await self.disconnect(server_name)

        try:
            # Handle OAuth authentication if configured
            auth_headers = {}
            if config.auth_type != AuthType.NONE and config.auth_config:
                handler = mcp_auth_manager.create_handler(server_name, config.auth_config)
                if handler:
                    logger.info(f"Authenticating with {server_name} using {config.auth_type}")
                    token = await mcp_auth_manager.authenticate(server_name)
                    auth_headers = mcp_auth_manager.get_headers(server_name)
                    logger.info(f"Successfully authenticated with {server_name}")

            # Merge auth headers into config headers
            if auth_headers:
                config.headers.update(auth_headers)

            # Create transport and session
            stack = AsyncExitStack()
            try:
                # 传输上下文必须在当前任务进入（SSE/stdio transport 的 task group
                # 生命周期绑定进入它的任务；放进 wait_for 子任务会跨任务销毁
                # cancel scope、杀死接收循环）。超时只包 initialize()。
                read, write = await stack.enter_async_context(
                    self._transport.create_transport(config)
                )
                session = await self._transport.create_session(
                    read,
                    write,
                    message_handler=self._build_message_handler(server_name),
                    timeout=self.MCP_CONNECT_TIMEOUT,
                )
                # Push session exit onto the same stack so teardown order is
                # guaranteed: session (stops receive loop) closes BEFORE the
                # transport's streams. Closing them separately would race the
                # still-cancelling receive loop with stream.aclose().
                stack.push_async_exit(session.__aexit__)

                self._stacks[server_name] = stack
                self._sessions[server_name] = session
                self._configs[server_name] = config
            except asyncio.TimeoutError:
                logger.error(
                    f"MCP connect to '{server_name}' timed out after "
                    f"{self.MCP_CONNECT_TIMEOUT}s — skipping this server (it must not "
                    f"block the core service)."
                )
                await stack.aclose()
                return ConnectionResult(
                    success=False,
                    server_name=server_name,
                    error=f"Connection timed out after {self.MCP_CONNECT_TIMEOUT}s",
                )
            except Exception:
                await stack.aclose()
                raise

            # Initialize features
            tools_feature = McpToolsFeature()
            await tools_feature.initialize(
                session,
                server_name,
                ensure_alive=self._ensure_session_alive,
                ensure_alive_force=self._ensure_alive_force,
            )
            self._tools_feature[server_name] = tools_feature

            resources_feature = McpResourcesFeature()
            await resources_feature.initialize(session, server_name)
            self._resources_feature[server_name] = resources_feature

            prompts_feature = McpPromptsFeature()
            await prompts_feature.initialize(session, server_name)
            self._prompts_feature[server_name] = prompts_feature

            # 保活：远程 servicer 会空闲关闭 SSE 连接，导致本地会话套接字进
            # CLOSE_WAIT、后续工具调用挂死。后台定期 ping 防空闲关闭；失败重连。
            asyncio.create_task(self._keepalive_loop(server_name, session))

            tools_count = len(tools_feature.get_tools())
            resources_count = len(resources_feature.get_resources())
            prompts_count = len(prompts_feature.get_prompts())

            logger.info(
                f"Connected to MCP server: {server_name} "
                f"({tools_count} tools, {resources_count} resources, {prompts_count} prompts)"
            )

            return ConnectionResult(
                success=True,
                server_name=server_name,
                tools_count=tools_count
            )

        except Exception as e:
            logger.exception(f"Error connecting to {server_name}: {e}")
            if "stack" in locals():
                await stack.aclose()
            return ConnectionResult(
                success=False,
                server_name=server_name,
                error=str(e)
            )

    async def _keepalive_loop(self, server_name: str, session: ClientSession) -> None:
        """保活后台任务：定期 ping 会话，防空闲被远端关闭（SSE CLOSE_WAIT 僵尸）。

        检测到失联后**主动安排重连**（独立任务里 disconnect + ensure_connected），
        而不是只记日志——否则"ping 通但会话已退化"的僵尸会话会一直拖到调用失败才
        重连。重连放独立任务：keepalive 任务本身不碰 disconnect，避免被会话拆除
        的 anyio 取消波及；重连由每 server 锁串行，且 ensure_connected 会为新会话
        重新拉起本保活任务。
        """
        while True:
            await asyncio.sleep(self.MCP_KEEPALIVE_INTERVAL)
            if self._sessions.get(server_name) is not session:
                break
            try:
                await asyncio.wait_for(
                    session.send_ping(),
                    timeout=self.MCP_PING_TIMEOUT,
                )
            except asyncio.CancelledError:
                break  # 任务被取消（会话拆除/进程关闭）
            except Exception:
                logger.warning(
                    f"[MCP] keepalive ping '{server_name}' 失败，安排后台重连"
                )
                asyncio.create_task(self._reconnect(server_name))
                break

    async def _reconnect(self, server_name: str) -> None:
        """后台重连：断开死会话并从缓存 config 重建（每 server 锁串行）。"""
        try:
            async with self._reconnect_locks.setdefault(server_name, asyncio.Lock()):
                try:
                    await self.disconnect(server_name)
                    await self._ensure_connected_isolated(server_name)
                except Exception:
                    logger.exception(f"[MCP] 后台重连 '{server_name}' 失败")
        except asyncio.CancelledError:
            # fire-and-forget 后台任务：进程/会话关闭时被取消是正常退出
            pass

    async def _ensure_connected_isolated(self, server_name: str) -> bool:
        """在一次性任务里执行 connect，使新会话的 task-group cancel scope
        绑定到该任务（任务完成后宿主已结束）。

        原因：``session.__aenter__()`` 会把会话的 receive-loop task group 的
        cancel scope 绑定到调用它的任务；若重连在长驻调用者（如测试任务、
        轮巡循环）里执行，后续其它任务的 ``disconnect`` 触发 ``cancel_scope.cancel()``
        会误取消该调用者。放到一次性任务里，宿主随之结束，取消即为 no-op。
        """
        task = asyncio.create_task(self.ensure_connected(server_name))
        try:
            return await task
        except BaseException:
            task.cancel()
            raise

    async def _ensure_session_alive(self, server_name: str) -> ClientSession | None:
        """工具调用前的保活检查：会话失联则重连，返回当前活会话。

        重连用每 server 一把锁串行，避免并发重连竞争。返回 None 表示连不上。
        """
        session = self._sessions.get(server_name)
        if session is None:
            async with self._reconnect_locks.setdefault(server_name, asyncio.Lock()):
                await self._ensure_connected_isolated(server_name)
            return self._sessions.get(server_name)
        try:
            await asyncio.wait_for(
                session.send_ping(),
                timeout=self.MCP_PING_TIMEOUT,
            )
            return session
        except Exception:
            logger.warning(f"[MCP] 会话 '{server_name}' 失联，调用前重连")
            async with self._reconnect_locks.setdefault(server_name, asyncio.Lock()):
                try:
                    # 先断开死会话，再 ensure_connected 从缓存 config 重连
                    # （避免 ensure_connected 先对死会话做 list_tools 健康检查而挂起）。
                    await self.disconnect(server_name)
                    await self._ensure_connected_isolated(server_name)
                except Exception:
                    logger.exception(f"[MCP] 调用前重连 '{server_name}' 失败")
            return self._sessions.get(server_name)

    async def _ensure_alive_force(self, server_name: str) -> ClientSession | None:
        """强制重连：不测 ping（可能"ping 通但会话已退化"），直接断开重建。

        供工具调用失败后的重试路径使用，返回新会话（重连失败返回 None）。
        """
        async with self._reconnect_locks.setdefault(server_name, asyncio.Lock()):
            try:
                await self.disconnect(server_name)
                await self._ensure_connected_isolated(server_name)
            except Exception:
                logger.exception(f"[MCP] 强制重连 '{server_name}' 失败")
        return self._sessions.get(server_name)

    async def connect_from_db(self, server_name: str) -> ConnectionResult:
        """
        Connect to a server using configuration from database.

        Args:
            server_name: Name of server in database

        Returns:
            ConnectionResult
        """
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(
                    McpServer.name == server_name,
                    McpServer.enabled
                )
            )
            server = result.scalars().first()

            if not server:
                return ConnectionResult(
                    success=False,
                    server_name=server_name,
                    error=f"Server '{server_name}' not found in database or disabled",
                )

            # Parse args and env
            args = self._parse_json_field(server.args, [])
            env = self._parse_json_field(server.env, {})

            # Determine transport type
            transport = TransportType.SSE if is_sse_url(server.command) else TransportType.STDIO

            config = McpServerConfig(
                name=server.name,
                transport=transport,
                command=server.command,
                url=server.command if transport == TransportType.SSE else None,
                args=args,
                env=env,
                enabled=server.enabled,
            )

            return await self.connect(config)

    async def connect_all(self) -> list[ConnectionResult]:
        """
        Connect to all enabled servers from database.
        Also handles legacy config migration.

        Returns:
            List of connection results
        """
        results = []

        # 1. Migrate legacy config if needed
        await self._seed_legacy_config()

        # 2. Fetch and connect all enabled servers
        async with session_scope() as session:
            result = await session.execute(select(McpServer).where(McpServer.enabled))
            servers = result.scalars().all()

            for server in servers:
                try:
                    result = await self.connect_from_db(server.name)
                    results.append(result)
                except Exception as e:
                    logger.exception(f"Failed to connect to MCP server '{server.name}': {e}")
                    results.append(ConnectionResult(
                        success=False,
                        server_name=server.name,
                        error=str(e)
                    ))

        return results

    async def connect_all_with_logging(self, mcp_results: list | None = None) -> None:
        """
        Run ``connect_all()`` in the background and log the summary.

        Called from APP_STARTED without awaiting, so a slow/hanging MCP server
        never blocks the core service startup. Each connection is still bounded
        by ``MCP_CONNECT_TIMEOUT``.
        """
        try:
            connect_results = await self.connect_all()
            connected = sum(1 for r in connect_results if r.success)
            logger.info(
                "[MCP] ✓ Servers initialized: %d, connected: %d/%d",
                len(mcp_results or []),
                connected,
                len(connect_results),
            )
            for r in connect_results:
                if not r.success:
                    logger.warning(
                        f"[MCP] Server '{r.server_name}' not connected: {r.error}"
                    )
        except Exception:
            logger.exception("[MCP] Background connect_all failed")

    def _build_message_handler(self, server_name: str):
        """构造 mcp ClientSession 的入站消息处理器。

        服务端主动推送的任意 notification（如 notifications/kf_new_message）会
        经由此 handler 以通用事件 ``MCP_SERVER_NOTIFICATION`` 分发到事件总线，
        method 与 payload 保留在 ``event.data`` 中，由各订阅方自行判断是否关心。
        MCP 客户端层不感知任何具体业务 method。

        注意：**派发绝不能阻塞 mcp 接收循环**。接收循环 ``await`` message_handler，
        若在这里 await 完整事件总线发布链，而某订阅方（如 kf 推送立即轮巡）又去
        调 MCP 工具（kf_list 等）——工具响应需要接收循环投递，形成死锁：轮巡等
        响应、接收循环等轮巡，最终 ping 响应也无人处理 → 被判死重连。因此这里
        只 ``create_task`` 后台派发，接收循环立即返回。
        """
        async def _on_message(message) -> None:
            # 兼容两种 root：标准类型（对象 .method / .root）与宽松类型（dict）
            root = getattr(message, "root", None)
            if isinstance(root, dict):
                method = root.get("method")
                payload = root.get("params")
            else:
                method = getattr(root, "method", None)
                payload = getattr(root, "params", None)

            # 仅分发服务端主动推送的 notification（method 以 notifications/ 前缀），
            # 请求/响应等其它消息不入事件总线。
            if not method or not str(method).startswith("notifications/"):
                return

            class McpServerNotificationEvent(BaseEvent):
                event_type: str = SystemEventType.MCP_SERVER_NOTIFICATION
                server_name: str
                method: str | None

            event = McpServerNotificationEvent(
                server_name=server_name,
                method=method,
                data=EventData.model_validate(
                    {"method": method, "payload": payload}
                ),
            )
            logger.info("MCP notification %s received from %s", method, server_name)
            try:
                # 后台派发：接收循环立即返回（不阻塞；阻塞会与轮巡里的 MCP 工具
                # 调用互等死锁，见上方 docstring）。
                asyncio.create_task(_safe_publish_notification(server_name, event))
            except Exception:
                logger.exception("Failed to dispatch MCP notification for %s", server_name)

        async def _safe_publish_notification(server_name: str, event) -> None:
            try:
                await system_bus.publish(event)
            except Exception:
                logger.exception("MCP notification dispatch failed for %s", server_name)

        return _on_message

    async def disconnect(self, server_name: str) -> None:
        """Disconnect a single server."""
        # 原子 pop：并发 disconnect（如后台 keepalive 重连与调用方同时断开）
        # 不会出现「检查存在→await→del」之间的竞态（KeyError）。
        stack = self._stacks.pop(server_name, None)
        if stack is not None:
            try:
                # The stack owns both the session and the transport, closing
                # them in registration order (session first, transport second).
                await stack.aclose()
            except Exception as e:
                logger.debug(f"Error closing stack for '{server_name}': {e}", exc_info=True)

        self._sessions.pop(server_name, None)
        self._tools_feature.pop(server_name, None)
        self._resources_feature.pop(server_name, None)
        self._prompts_feature.pop(server_name, None)
        self._health_checker.reset(server_name)

        logger.info(f"Disconnected MCP server: {server_name}")

    async def disconnect_all(self) -> None:
        """Disconnect all servers."""
        for name in list(self._stacks.keys()):
            await self.disconnect(name)

    async def cleanup(self) -> None:
        """Alias for disconnect_all (for backward compatibility)."""
        await self.disconnect_all()

    # ═══════════════════════════════════════════════════════════
    # Health & Reconnection
    # ═══════════════════════════════════════════════════════════

    async def health_check(self, server_name: str) -> HealthStatus:
        """Check health of a server."""
        session = self._sessions.get(server_name)
        return await self._health_checker.check(server_name, session)

    async def ensure_connected(self, server_name: str) -> bool:
        """
        Ensure server is connected, reconnect if necessary.

        Args:
            server_name: Server to check/connect

        Returns:
            True if connected after this call
        """
        # Check existing connection
        if server_name in self._sessions:
            health = await self.health_check(server_name)
            if health.is_healthy:
                return True
            logger.info(f"Stale session for '{server_name}', reconnecting...")
            await self.disconnect(server_name)

        # Try reconnect from cached config
        if server_name in self._configs:
            result = await self.connect(self._configs[server_name])
            return result.success

        # Try load from DB
        result = await self.connect_from_db(server_name)
        return result.success

    # ═══════════════════════════════════════════════════════════
    # Tool Access
    # ═══════════════════════════════════════════════════════════

    @property
    def sessions(self) -> dict[str, Any]:
        """Access sessions dict (for backward compatibility)."""
        return self._sessions

    @property
    def _server_configs(self) -> dict[str, McpServerConfig]:
        """Access configs (for backward compatibility)."""
        return self._configs

    async def get_tools(self, server_name: str | None = None) -> list[EvoLoopTool]:
        """
        Get tools for a specific server, or all tools if no server specified.

        Args:
            server_name: Server name (optional, None = get all)

        Returns:
            List of native tools
        """
        if server_name is None:
            # Return all tools from all connected servers
            return await self.aget_all_tools()

        if await self.ensure_connected(server_name):
            feature = self._tools_feature.get(server_name)
            if feature:
                return feature.get_tools()
        return []

    async def aget_all_tools(self) -> list[EvoLoopTool]:
        """Get all tools from all connected servers, ensuring connections are alive.

        Only iterates servers already connected (in ``_configs``). Connection is
        established by connect_all() at a controlled point (e.g. a lazily-bound
        first use in the current loop), not re-seeded on every call.
        """
        all_tools = []
        for server_name in list(self._configs.keys()):
            if await self.ensure_connected(server_name):
                feature = self._tools_feature.get(server_name)
                if feature:
                    all_tools.extend(feature.get_tools())
        return all_tools

    # ═══════════════════════════════════════════════════════════
    # Resources Access
    # ═══════════════════════════════════════════════════════════

    async def list_resources(self, server_name: str) -> list[McpResource]:
        """
        List available resources from a server.

        Args:
            server_name: Server name

        Returns:
            List of resource info dicts
        """
        if await self.ensure_connected(server_name):
            feature = self._resources_feature.get(server_name)
            if feature:
                resources = feature.get_resources()
                return [
                    McpResource(
                        uri=str(r.uri),
                        name=r.name,
                        mimeType=r.mimeType,
                        description=r.description,
                    )
                    for r in resources
                ]
        return []

    async def read_resource(self, server_name: str, uri: str) -> McpResourceContent:
        """
        Read content from a resource URI.

        Args:
            server_name: Server name
            uri: Resource URI to read

        Returns:
            Dict with content and metadata
        """
        if await self.ensure_connected(server_name):
            feature = self._resources_feature.get(server_name)
            if feature:
                return await feature.read_resource(uri)
        raise RuntimeError(f"Server '{server_name}' not connected or resources not available")

    def get_resources_formatted(self, server_name: str) -> str:
        """
        Get formatted markdown list of resources.

        Args:
            server_name: Server name

        Returns:
            Markdown formatted string
        """
        feature = self._resources_feature.get(server_name)
        if feature:
            return feature.format_resources_list()
        return "*Server not connected*"

    # ═══════════════════════════════════════════════════════════
    # Prompts Access
    # ═══════════════════════════════════════════════════════════

    async def list_prompts(self, server_name: str) -> list[McpPrompt]:
        """
        List available prompts from a server.

        Args:
            server_name: Server name

        Returns:
            List of prompt info dicts
        """
        if await self.ensure_connected(server_name):
            feature = self._prompts_feature.get(server_name)
            if feature:
                prompts = feature.get_prompts()
                return [
                    McpPrompt(
                        name=p.name,
                        description=p.description,
                        arguments=[
                            McpPromptArgument(name=arg.name, required=arg.required)
                            for arg in (p.arguments or [])
                        ],
                    )
                    for p in prompts
                ]
        return []

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict[str, str] | None = None,
    ) -> McpPromptResult:
        """
        Get a rendered prompt with optional arguments.

        Args:
            server_name: Server name
            prompt_name: Prompt name
            arguments: Optional arguments for the prompt

        Returns:
            Dict with prompt messages and metadata
        """
        if await self.ensure_connected(server_name):
            feature = self._prompts_feature.get(server_name)
            if feature:
                return await feature.get_prompt(prompt_name, arguments)
        raise RuntimeError(f"Server '{server_name}' not connected or prompts not available")

    def get_prompts_formatted(self, server_name: str) -> str:
        """
        Get formatted markdown list of prompts.

        Args:
            server_name: Server name

        Returns:
            Markdown formatted string
        """
        feature = self._prompts_feature.get(server_name)
        if feature:
            return feature.format_prompts_list()
        return "*Server not connected*"

    # ═══════════════════════════════════════════════════════════
    # Server Management
    # ═══════════════════════════════════════════════════════════

    async def add_server(self, name: str, details: dict[str, Any]) -> ConnectionResult:
        """Add server to DB and connect (unless disabled)."""
        enabled = bool(details.get("enabled", True))
        # Update DB
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(McpServer.name == name)
            )
            db_server = result.scalars().first()

            args_json = json.dumps(details.get("args", []))
            env_json = json.dumps(details.get("env", {}))

            if db_server:
                db_server.command = details.get("command")
                db_server.args = args_json
                db_server.env = env_json
                db_server.enabled = enabled
            else:
                db_server = McpServer(
                    name=name,
                    command=details.get("command"),
                    args=args_json,
                    env=env_json,
                    enabled=enabled,
                )
                session.add(db_server)

        # Disabled server: store config only, do not connect
        if not enabled:
            await self.disconnect(name)
            return ConnectionResult(
                success=True,
                server_name=name,
                tools_count=0,
                error=None,
            )

        # Connect
        transport = TransportType.SSE if is_sse_url(details.get("command")) else TransportType.STDIO

        config = McpServerConfig(
            name=name,
            transport=transport,
            command=details.get("command"),
            url=details.get("command") if transport == TransportType.SSE else None,
            args=details.get("args", []),
            env=details.get("env", {}),
            enabled=True,
        )

        return await self.connect(config)

    async def remove_server(self, name: str) -> bool:
        """Remove server from DB and disconnect."""
        await self.disconnect(name)

        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(McpServer.name == name)
            )
            server = result.scalars().first()
            if server:
                await session.delete(server)
                return True
        return False

    async def list_servers(self) -> list[McpServerSummary]:
        """List all servers with status."""
        async with session_scope() as session:
            result = await session.execute(select(McpServer))
            servers = result.scalars().all()

            output = []
            for s in servers:
                is_connected = s.name in self._sessions
                feature = self._tools_feature.get(s.name)
                tools_count = len(feature.get_tools()) if feature else 0

                output.append(
                    McpServerSummary(
                        name=s.name,
                        command=s.command,
                        status="connected" if is_connected else "available",
                        tools_count=tools_count,
                        enabled=s.enabled,
                    )
                )
            return output

    def get_connection_state(self, server_name: str) -> ConnectionState:
        """Get current connection state for a server."""
        is_connected = server_name in self._sessions
        feature = self._tools_feature.get(server_name)

        return ConnectionState(
            server_name=server_name,
            is_connected=is_connected,
            last_health_check=self._health_checker.get_last_check_time(server_name),
            tools_count=len(feature.get_tools()) if feature else 0,
        )

    # ═══════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════

    async def _seed_legacy_config(self) -> None:
        """Migrate legacy JSON config to database."""
        async with session_scope() as session:
            result = await session.execute(select(McpServer))
            if result.first() is not None:
                return

            if not os.path.exists(self._legacy_config_path):
                return

            logger.info("Migrating legacy MCP config to database...")
            try:
                with open(self._legacy_config_path, encoding="utf-8") as f:
                    config = json.load(f)
                    servers = config.get("mcpServers", {})

                    for name, details in servers.items():
                        new_server = McpServer(
                            name=name,
                            command=details.get("command"),
                            args=json.dumps(details.get("args", [])),
                            env=json.dumps(details.get("env", {})),
                            enabled=True,
                        )
                        session.add(new_server)
                logger.info("Legacy MCP config migrated successfully.")
            except Exception as e:
                logger.exception(f"Failed to migrate legacy config: {e}")

    @staticmethod
    def _parse_json_field(value: Any, default: Any) -> Any:
        """Parse JSON string field."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return value if value is not None else default


# Singleton instance
mcp_client_manager = McpClientManager()
