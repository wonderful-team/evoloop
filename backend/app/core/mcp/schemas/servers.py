"""MCP server configuration schemas."""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class McpServerBase(DynamicBaseModel):
    name: str
    command: str
    args: list[str] | None = []
    env: dict[str, str] | None = {}


class McpServerCreate(McpServerBase):
    pass


class McpServerRead(McpServerBase):
    id: int
    status: str
    tools_count: int


class McpServerUpdate(DynamicBaseModel):
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None


class ServerCapabilities(DynamicBaseModel):
    """Capabilities reported by an MCP server."""


class McpServerConfig(DynamicBaseModel):
    """Configuration for an MCP server connection."""

    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth_type: str = "none"
    auth_config: dict[str, Any] = Field(default_factory=dict)
    auto_connect: bool = True
    enabled: bool = True


class ConnectionState(DynamicBaseModel):
    """Connection state tracking."""

    server_name: str
    is_connected: bool = False
    last_health_check: float | None = None
    tools_count: int = 0
    error_message: str | None = None


class ConnectionResult(DynamicBaseModel):
    """Result of a connection attempt."""

    success: bool
    server_name: str
    tools_count: int = 0
    error: str | None = None
    capabilities: ServerCapabilities | None = None


class WorkerMcpServerConfig(DynamicBaseModel):
    """MCP server configuration for a specific Worker."""

    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth_type: str = "none"
    auth_config: dict[str, Any] = Field(default_factory=dict)
    inherit_from_global: bool = False


class WorkerMcpConfig(DynamicBaseModel):
    """MCP configuration for a Worker."""

    servers: list[WorkerMcpServerConfig] = Field(default_factory=list)
    inherit_servers: list[str] = Field(default_factory=list)
    auto_connect: bool = True


class HealthStatus(DynamicBaseModel):
    """Health check result."""

    is_healthy: bool
    server_name: str
    last_check: float
    response_time_ms: float
    error_message: str | None = None
