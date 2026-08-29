"""Health checking for MCP connections."""

import asyncio
import logging
import time

from mcp import ClientSession

from app.core.mcp.schemas import HealthStatus
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class McpHealthChecker:
    """Health checker for MCP server connections."""

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self._last_check: dict[str, float] = {}

    async def check(self, server_name: str, session: ClientSession) -> HealthStatus:
        """
        Check health of a session by listing tools.

        Args:
            server_name: Server identifier
            session: Active MCP ClientSession

        Returns:
            HealthStatus with check results
        """
        if not session:
            return HealthStatus(
                is_healthy=False,
                server_name=server_name,
                last_check=time.time(),
                response_time_ms=0.0,
                error_message="No session available",
            )

        start_time = time.time()

        try:
            # Use list_tools as health check。注意：退化会话上 list_tools 会挂起
            # （"ping 通但会话已退化"），必须加超时，否则死会话上的健康检查会
            # 永久阻塞调用方（如推送轮巡），拖死整个值守调度器。
            await asyncio.wait_for(
                session.list_tools(),
                timeout=self.timeout_seconds,
            )

            response_time = elapsed_ms(start_time)
            self._last_check[server_name] = time.time()

            return HealthStatus(
                is_healthy=True,
                server_name=server_name,
                last_check=time.time(),
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = elapsed_ms(start_time)
            logger.warning(
                f"Health check failed for MCP server '{server_name}': {e}",
                exc_info=True,
            )

            return HealthStatus(
                is_healthy=False,
                server_name=server_name,
                last_check=time.time(),
                response_time_ms=response_time,
                error_message=str(e),
            )

    def get_last_check_time(self, server_name: str) -> float | None:
        """Get timestamp of last successful health check."""
        return self._last_check.get(server_name)

    def reset(self, server_name: str) -> None:
        """Reset health check tracking for a server."""
        self._last_check.pop(server_name, None)
