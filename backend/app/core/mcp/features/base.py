"""Base class for MCP features (tools, resources, prompts)."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from mcp import ClientSession


class McpFeature(ABC):
    """Base class for MCP protocol features."""
    
    @property
    @abstractmethod
    def feature_name(self) -> str:
        """Feature name: tools, resources, prompts, etc."""
        pass
    
    @abstractmethod
    async def initialize(self, session: ClientSession, server_name: str) -> None:
        """
        Initialize feature with a session.
        
        Args:
            session: Active MCP ClientSession
            server_name: Name of the connected server
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> dict[str, Any]:
        """Get feature capabilities."""
        pass
    
    def reset(self) -> None:
        """Reset feature state (called on disconnect)."""
        pass


class McpFeatureNotSupportedError(Exception):
    """Raised when a feature is not supported by the server."""
    pass
