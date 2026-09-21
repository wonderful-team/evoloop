"""MCP configuration models and types."""

from enum import Enum
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.http import is_http_url


def is_sse_url(command: str | None) -> bool:
    """Check if a command string represents an SSE transport URL."""
    return bool(command and is_http_url(command))


def is_streamable_http_url(command: str | None) -> bool:
    """Check if a command string represents a Streamable HTTP transport URL.

    约定：以 ``/mcp`` 结尾（或路径 basename 为 mcp）的 http URL 视为
    Streamable HTTP 端点；否则回退为 SSE（向后兼容）。
    """
    if not command or not is_http_url(command):
        return False
    path = command.split("?", 1)[0].rstrip("/")
    return path.endswith("/mcp")


class ServerCapabilities(DynamicBaseModel):
    """Capabilities reported by an MCP server."""


class TransportType(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


def normalize_transport(value: str | None) -> TransportType:
    """Normalize transport string to TransportType enum."""
    if not value:
        return TransportType.STDIO
    normalized = value.lower().replace("-", "_")
    if normalized in ("streamable_http", "streamablehttp"):
        return TransportType.STREAMABLE_HTTP
    try:
        return TransportType(normalized)
    except ValueError:
        return TransportType.STDIO


class AuthType(str, Enum):
    """Authentication types for MCP servers."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH_AUTHORIZATION_CODE = "oauth_auth_code"
    OAUTH_DEVICE_CODE = "oauth_device_code"


class McpServerConfig(DynamicBaseModel):
    """Configuration for an MCP server connection."""

    name: str
    transport: TransportType = TransportType.STDIO
    # Stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # SSE transport
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    # Authentication
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
    # Behavior
    auto_connect: bool = True
    enabled: bool = True

    @classmethod
    def from_db_model(cls, server: Any) -> "McpServerConfig":
        """Create config from database model."""
        import json

        # Parse args
        args = server.args
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError, ValueError):
                args = []

        # Parse env
        env = server.env
        if isinstance(env, str):
            try:
                env = json.loads(env)
            except (json.JSONDecodeError, TypeError, ValueError):
                env = {}

        # Parse headers
        headers = {}
        if hasattr(server, "headers") and server.headers:
            try:
                headers = json.loads(server.headers) if isinstance(server.headers, str) else server.headers
            except (json.JSONDecodeError, TypeError, ValueError):
                headers = {}

        # Parse auth config if stored
        auth_config_data = {}
        auth_type = AuthType.NONE
        if hasattr(server, "auth_config") and server.auth_config:
            try:
                auth_config_data = (
                    json.loads(server.auth_config)
                    if isinstance(server.auth_config, str)
                    else server.auth_config
                )
                auth_type = AuthType(auth_config_data.get("method", "none"))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        # Determine transport
        explicit_transport = normalize_transport(getattr(server, "transport", None))
        if explicit_transport != TransportType.STDIO:
            transport = explicit_transport
        elif is_streamable_http_url(server.command):
            transport = TransportType.STREAMABLE_HTTP
        elif is_sse_url(server.command):
            transport = TransportType.SSE
        else:
            transport = TransportType.STDIO

        return cls(
            name=server.name,
            transport=transport,
            command=server.command,
            url=server.command if transport != TransportType.STDIO else None,
            args=args or [],
            env=env or {},
            headers=headers,
            enabled=server.enabled,
            auth_type=auth_type,
            auth_config=auth_config_data,
        )

    def validate(self) -> None:
        """Validate configuration."""
        if self.transport == TransportType.STDIO:
            if not self.command:
                raise ValueError(
                    f"MCP server '{self.name}': command is required for stdio transport"
                )
        elif self.transport in (TransportType.SSE, TransportType.STREAMABLE_HTTP):
            if not self.url:
                raise ValueError(
                    f"MCP server '{self.name}': url is required for {self.transport} transport"
                )


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
