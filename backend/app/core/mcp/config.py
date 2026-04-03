"""MCP configuration models and types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


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


@dataclass
class McpServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    transport: TransportType = TransportType.STDIO
    # Stdio transport
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # SSE transport
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    # Authentication
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = field(default_factory=dict)
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
        auth_config = {}
        auth_type = AuthType.NONE
        if hasattr(server, 'auth_config') and server.auth_config:
            try:
                auth_config = json.loads(server.auth_config) if isinstance(server.auth_config, str) else server.auth_config
                auth_type = AuthType(auth_config.get('method', 'none'))
            except:
                pass
        
        # Determine transport
        transport = TransportType.SSE if (
            server.command and (
                server.command.startswith("http://") or 
                server.command.startswith("https://")
            )
        ) else TransportType.STDIO
        
        return cls(
            name=server.name,
            transport=transport,
            command=server.command,
            args=args or [],
            env=env or {},
            enabled=server.enabled,
            auth_type=auth_type,
            auth_config=auth_config,
        )

    def validate(self) -> None:
        """Validate configuration."""
        if self.transport == TransportType.STDIO:
            if not self.command:
                raise ValueError(f"MCP server '{self.name}': command is required for stdio transport")
        elif self.transport == TransportType.SSE:
            if not self.url:
                raise ValueError(f"MCP server '{self.name}': url is required for sse transport")


@dataclass
class ConnectionState:
    """Connection state tracking."""
    server_name: str
    is_connected: bool = False
    last_health_check: Optional[float] = None
    tools_count: int = 0
    error_message: Optional[str] = None


@dataclass
class ConnectionResult:
    """Result of a connection attempt."""
    success: bool
    server_name: str
    tools_count: int = 0
    error: Optional[str] = None
    capabilities: Optional[dict] = None
