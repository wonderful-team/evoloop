"""Base class for MCP features (tools, resources, prompts)."""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from mcp import ClientSession
from pydantic import BaseModel, ConfigDict, Field

from app.utils.model_helpers import LegacyDictMixin


class McpFeatureCapabilities(BaseModel, LegacyDictMixin):
    """Dynamic capabilities for an MCP feature."""
    model_config = ConfigDict(extra="allow")


class McpResourceContent(BaseModel, LegacyDictMixin):
    """Content returned from reading an MCP resource."""
    model_config = ConfigDict(extra="allow")
    uri: str = ""
    content: str = ""
    mime_type: Optional[str] = None
    is_binary: bool = False


class McpPromptMessage(BaseModel, LegacyDictMixin):
    """A single message within an MCP prompt result."""
    model_config = ConfigDict(extra="allow")
    role: str
    content: Optional[str] = None
    content_type: Optional[str] = None
    mime_type: Optional[str] = None
    resource_uri: Optional[str] = None


class McpPromptResult(BaseModel, LegacyDictMixin):
    """Result of getting a rendered MCP prompt."""
    model_config = ConfigDict(extra="allow")
    name: str = ""
    description: Optional[str] = None
    messages: List[McpPromptMessage] = Field(default_factory=list)


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
    async def get_capabilities(self) -> McpFeatureCapabilities:
        """Get feature capabilities."""
        pass
    
    def reset(self) -> None:
        """Reset feature state (called on disconnect)."""
        pass


class McpFeatureNotSupportedError(Exception):
    """Raised when a feature is not supported by the server."""
    pass
