"""Configuration models for Worker-specific MCP."""

from typing import Any, Dict, List, Optional

from pydantic import Field

from app.core.mcp.config import AuthType, McpServerConfig, TransportType
from app.infrastructure.pydantic_base import DynamicBaseModel


class WorkerMcpServerConfig(DynamicBaseModel):
    """MCP server configuration for a specific Worker."""
    name: str
    # Connection
    transport: TransportType = TransportType.STDIO
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    # Auth
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
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
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerMcpServerConfig":
        """Create from dict (e.g., from YAML config)."""
        transport = TransportType(data.get("transport", "stdio"))
        auth_data = data.get("auth", {})
        auth_type = AuthType(auth_data.get("method", "none"))

        return cls(
            name=data["name"],
            transport=transport,
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
            auth_type=auth_type,
            auth_config=auth_data,
            inherit_from_global=data.get("inherit_from_global", False),
        )


class WorkerMcpConfig(DynamicBaseModel):
    """MCP configuration for a Worker."""
    # Worker-specific MCP servers
    servers: List[WorkerMcpServerConfig] = Field(default_factory=list)
    # Global MCP servers to inherit
    inherit_servers: List[str] = Field(default_factory=list)
    # Auto-connect on worker start
    auto_connect: bool = True
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "WorkerMcpConfig":
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
    def from_skill_config(cls, skill_config: Dict[str, Any]) -> "WorkerMcpConfig":
        """Extract MCP config from Skill configuration."""
        mcp_data = skill_config.get("mcp", {})
        return cls.from_dict(mcp_data)
    
    def is_empty(self) -> bool:
        """Check if no MCP configuration."""
        return not self.servers and not self.inherit_servers
