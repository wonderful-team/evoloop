"""Transport layer for MCP connections (stdio and SSE)."""

import logging
import os
import sys
from contextlib import contextmanager
from types import TracebackType
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.core.mcp.config import McpServerConfig, TransportType, is_sse_url

logger = logging.getLogger(__name__)


@contextmanager
def restore_std_streams():
    """
    Temporarily restore sys.stdout and sys.stderr to original streams.
    This fixes issues where libraries (like Celery) monkey-patch stdout/stderr with proxies
    that don't implement fileno(), causing subprocess creation to fail.
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        if sys.__stdout__:
            sys.stdout = sys.__stdout__
        if sys.__stderr__:
            sys.stderr = sys.__stderr__
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


class TransportContext:
    """Class-based async context manager for MCP transport.

    Delegates directly to the SDK's own async context managers (``stdio_client`` /
    ``sse_client``). A generator-based ``asynccontextmanager`` wrapper would be
    torn down with ``GeneratorExit`` injected at its ``yield`` site, which races
    the SDK's internal anyio task group cancel scope during ``AsyncExitStack.aclose()``
    ("Attempted to exit a cancel scope that isn't the current task's current cancel scope").
    """

    def __init__(self, config: McpServerConfig):
        self._config = config
        self._cm: Any = None

    async def __aenter__(self) -> tuple[Any, Any]:
        if self._config.transport == TransportType.SSE or is_sse_url(self._config.command):
            url = self._config.url or self._config.command
            logger.info(f"Connecting via SSE to {url}")
            self._cm = sse_client(url, headers=self._config.headers)
        else:
            full_env = os.environ.copy()
            full_env.update(self._config.env)
            server_params = StdioServerParameters(
                command=self._config.command,
                args=self._config.args,
                env=full_env,
            )
            logger.info(f"Connecting via stdio to {self._config.command}")
            with restore_std_streams():
                self._cm = stdio_client(server_params)
        return await self._cm.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if self._cm is None:
            return None
        try:
            return await self._cm.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self._cm = None


class McpTransport:
    """Transport layer for MCP connections."""

    @staticmethod
    def create_transport(config: McpServerConfig) -> TransportContext:
        """
        Create transport (read/write streams) based on config.

        Args:
            config: Server configuration

        Returns:
            Async context manager yielding a (read_stream, write_stream) tuple.
        """
        return TransportContext(config)

    @staticmethod
    async def create_session(read_stream: Any, write_stream: Any) -> ClientSession:
        """
        Create and initialize a ClientSession.

        mcp>=1.26 的 BaseSession 只在 `__aenter__` 时启动 `_receive_loop` 任务组；
        若不进入 session 上下文，服务端响应永远不会被处理，initialize() 将永久挂起。

        Args:
            read_stream: Read stream from transport
            write_stream: Write stream from transport

        Returns:
            Initialized ClientSession
        """
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        return session
