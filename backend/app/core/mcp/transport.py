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
from pydantic import RootModel

from app.core.mcp.config import McpServerConfig, TransportType, is_sse_url

logger = logging.getLogger(__name__)

_PATCHED_NOTIFICATION_TYPE = False


class _LooseServerNotification(RootModel[Any]):
    """宽松的 ServerNotification：接受任意自定义 notification。

    mcp 1.26 的 ClientSession 硬编码 ``types.ServerNotification``（9 个已知类型的
    Union），服务端推送的自定义 method（如 notifications/kf_new_message）会在
    ``model_validate`` 阶段校验失败被丢弃。此类型接受任意 payload，使自定义
    notification 能进入 ``_received_notification`` / ``message_handler``。
    """

    @property
    def method(self) -> str | None:
        root = self.root
        return root.get("method") if isinstance(root, dict) else getattr(root, "method", None)


def _patch_receive_notification_type() -> None:
    """把 ClientSession 的 notification 校验类型替换为宽松类型（幂等）。"""
    global _PATCHED_NOTIFICATION_TYPE
    if _PATCHED_NOTIFICATION_TYPE:
        return

    original_init = ClientSession.__init__

    def _patched_init(self, read_stream, write_stream, *args, **kwargs):
        # 替换传给 BaseSession 的 notification 校验类型
        kwargs.pop("_receive_notification_type", None)
        # 通过注入方式：先调用原始 init，再覆盖内部类型属性
        original_init(self, read_stream, write_stream, *args, **kwargs)
        self._receive_notification_type = _LooseServerNotification  # type: ignore[attr-defined]

    ClientSession.__init__ = _patched_init
    _PATCHED_NOTIFICATION_TYPE = True
    logger.info("MCP ClientSession notification 类型已替换为宽松类型（支持自定义推送）")


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
    async def create_session(read_stream: Any, write_stream: Any, message_handler: Any | None = None) -> ClientSession:
        """
        Create and initialize a ClientSession.

        mcp>=1.26 的 BaseSession 只在 `__aenter__` 时启动 `_receive_loop` 任务组；
        若不进入 session 上下文，服务端响应永远不会被处理，initialize() 将永久挂起。

        服务端主动推送的自定义 notification（如 notifications/kf_new_message）：
        mcp 1.26 的 ClientSession 硬编码 ``types.ServerNotification`` 校验，未知
        method 会在类型校验阶段抛异常被丢弃。这里 monkey-patch 一个宽松类型，
        使自定义 notification 能通过校验并分发到 ``message_handler``。

        Args:
            read_stream: Read stream from transport
            write_stream: Write stream from transport
            message_handler: 可选入站消息处理器（mcp ClientSession.message_handler）。

        Returns:
            Initialized ClientSession
        """
        _patch_receive_notification_type()

        session = ClientSession(read_stream, write_stream, message_handler=message_handler)
        await session.__aenter__()
        await session.initialize()
        return session
