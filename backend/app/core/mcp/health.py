"""Health checking for MCP connections."""

import logging
import time
from typing import Optional

from mcp import ClientSession

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class HealthStatus(DynamicBaseModel):
    """Health check result."""
    is_healthy: bool
    server_name: str
    last_check: float
    response_time_ms: float
    error_message: Optional[str] = None


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
                error_message="No session available"
            )
        
        start_time = time.time()
        
        try:
            # Use list_tools as health check
            await session.list_tools()
            
            response_time = (time.time() - start_time) * 1000
            self._last_check[server_name] = time.time()
            
            return HealthStatus(
                is_healthy=True,
                server_name=server_name,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.warning(f"Health check failed for MCP server '{server_name}': {e}")
            
            return HealthStatus(
                is_healthy=False,
                server_name=server_name,
                last_check=time.time(),
                response_time_ms=response_time,
                error_message=str(e)
            )
    
    def get_last_check_time(self, server_name: str) -> Optional[float]:
        """Get timestamp of last successful health check."""
        return self._last_check.get(server_name)
    
    def is_stale(self, server_name: str, max_age_seconds: float = 300.0) -> bool:
        """
        Check if health status is stale.
        
        Args:
            server_name: Server identifier
            max_age_seconds: Maximum age before considered stale
            
        Returns:
            True if no recent health check
        """
        last_check = self._last_check.get(server_name)
        if not last_check:
            return True
        return (time.time() - last_check) > max_age_seconds
    
    def reset(self, server_name: str) -> None:
        """Reset health check tracking for a server."""
        self._last_check.pop(server_name, None)
