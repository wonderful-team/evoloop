"""Configuration models for Worker-specific MCP."""

from dataclasses import dataclass, field
from typing import Any

from app.core.mcp.config import AuthType, McpServerConfig, TransportType


@dataclass
class WorkerMcpServerConfig:
    """MCP server configuration for a specific Worker."""
    name: str
    # Connection
    transport: TransportType = TransportType.STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # Auth
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = field(default_factory=dict)
    # Inheritance
    inherit_from_global: bool = False  # If True, reuse global connection
    
    def to_mcp_config(self) -> McpServerConfig:
        """Convert to standard McpServerConfig."""
        return McpServerConfig(
            name=self.name,
            transport=self.transport,
            command=self.command,
            args=self.args,
            env=self.env,
            url=self.url,
            headers=self.headers,
            auth_type=self.auth_type,
            auth_config=self.auth_config,
            enabled=True,
        )
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkerMcpServerConfig":
        """Create from dict (e.g., from YAML config)."""
        transport = TransportType(data.get("transport", "stdio"))
        auth_type = AuthType(data.get("auth", {}).get("method", "none"))
        
        return cls(
            name=data["name"],
            transport=transport,
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
            auth_type=auth_type,
            auth_config=data.get("auth", {}),
            inherit_from_global=data.get("inherit_from_global", False),
        )


@dataclass
class WorkerMcpConfig:
    """MCP configuration for a Worker."""
    # Worker-specific MCP servers
    servers: list[WorkerMcpServerConfig] = field(default_factory=list)
    # Global MCP servers to inherit
    inherit_servers: list[str] = field(default_factory=list)
    # Auto-connect on worker start
    auto_connect: bool = True
    
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WorkerMcpConfig":
        """Create from dict (e.g., from Skill YAML)."""
        if not data:
            return cls()
        
        servers = [
            WorkerMcpServerConfig.from_dict(s) 
            for s in data.get("servers", [])
        ]
        
        return cls(
            servers=servers,
            inherit_servers=data.get("inherit", []),
            auto_connect=data.get("auto_connect", True),
        )
    
    @classmethod
    def from_skill_config(cls, skill_config: dict[str, Any]) -> "WorkerMcpConfig":
        """Extract MCP config from Skill configuration."""
        mcp_data = skill_config.get("mcp", {})
        return cls.from_dict(mcp_data)
    
    def is_empty(self) -> bool:
        """Check if no MCP configuration."""
        return not self.servers and not self.inherit_servers
