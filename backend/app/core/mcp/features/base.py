"""Base class for MCP features (tools, resources, prompts)."""

import re
from abc import ABC, abstractmethod

from mcp import ClientSession
from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.mcp.schemas import McpFeatureCapabilities, McpResourceContent, McpPromptMessage, McpPromptResult

MCP_TOOL_NAME_PREFIX = "mcp__"
MCP_TOOL_NAME_SEPARATOR = "__"


def format_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Format tool name to standardized format: mcp__{server}__{tool}.
    OpenAI restriction: ^[a-zA-Z0-9_-]{1,64}$
    """
    safe_server = re.sub(r"[^a-zA-Z0-9_]", "_", server_name).lower()
    safe_tool = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name).lower()
    formatted = f"{MCP_TOOL_NAME_PREFIX}{safe_server}{MCP_TOOL_NAME_SEPARATOR}{safe_tool}"
    return formatted[:64]


def parse_mcp_tool_name(formatted_name: str) -> tuple[str, str] | None:
    """Parse a formatted MCP tool name into (server_name, tool_name)."""
    if not formatted_name.startswith(MCP_TOOL_NAME_PREFIX):
        return None
    parts = formatted_name[len(MCP_TOOL_NAME_PREFIX):].split(MCP_TOOL_NAME_SEPARATOR, 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


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
