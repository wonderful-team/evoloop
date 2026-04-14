"""MCP configuration models and types."""

from enum import Enum
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.infrastructure.pydantic_base import DynamicBaseModel


def is_sse_url(command: str | None) -> bool:
    """Check if a command string represents an SSE transport URL."""
    return bool(command and command.startswith(("http://", "https://")))


class ServerCapabilities(DynamicBaseModel):
    """Capabilities reported by an MCP server."""


class TransportType(str, Enum):
    """MCP transport types."""
    STDIO = "stdio"
    SSE = "sse"


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
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    # SSE transport
    url: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
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
            except:
                args = []
        
        # Parse env
        env = server.env
        if isinstance(env, str):
            try:
                env = json.loads(env)
            except:
                env = {}
        
        # Parse auth config if stored
        auth_config_data = {}
        auth_type = AuthType.NONE
        if hasattr(server, 'auth_config') and server.auth_config:
            try:
                auth_config_data = json.loads(server.auth_config) if isinstance(server.auth_config, str) else server.auth_config
                auth_type = AuthType(auth_config_data.get('method', 'none'))
            except:
                pass
        
        # Determine transport
        transport = TransportType.SSE if is_sse_url(server.command) else TransportType.STDIO
        
        return cls(
            name=server.name,
            transport=transport,
            command=server.command,
            args=args or [],
            env=env or {},
            enabled=server.enabled,
            auth_type=auth_type,
            auth_config=auth_config_data,
        )

    def validate(self) -> None:
        """Validate configuration."""
        if self.transport == TransportType.STDIO:
            if not self.command:
                raise ValueError(f"MCP server '{self.name}': command is required for stdio transport")
        elif self.transport == TransportType.SSE:
            if not self.url:
                raise ValueError(f"MCP server '{self.name}': url is required for sse transport")


class ConnectionState(DynamicBaseModel):
    """Connection state tracking."""
    server_name: str
    is_connected: bool = False
    last_health_check: Optional[float] = None
    tools_count: int = 0
    error_message: Optional[str] = None


class ConnectionResult(DynamicBaseModel):
    """Result of a connection attempt."""
    success: bool
    server_name: str
    tools_count: int = 0
    error: Optional[str] = None
    capabilities: Optional[ServerCapabilities] = None
