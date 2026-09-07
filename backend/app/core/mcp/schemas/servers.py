"""MCP server configuration schemas.

NOTE: This module only defines the server CRUD DTOs (McpServer*) and HealthStatus
that have no other canonical home. Shared MCP models (ServerCapabilities,
McpServerConfig, ConnectionState, ConnectionResult) are defined in their
canonical modules and re-exported via ``app.core.mcp.schemas`` — do NOT redefine
them here to avoid duplication.
"""

from app.infrastructure.pydantic_base import DynamicBaseModel


class McpServerBase(DynamicBaseModel):
    name: str
    command: str
    args: list[str] | None = []
    env: dict[str, str] | None = {}
    headers: dict[str, str] | None = {}
    enabled: bool = True


class McpServerCreate(McpServerBase):
    pass


class HealthStatus(DynamicBaseModel):
    """Health check result."""

    is_healthy: bool
    server_name: str
    last_check: float
    response_time_ms: float
    error_message: str | None = None
