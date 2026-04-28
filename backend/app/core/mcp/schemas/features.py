"""MCP feature schemas."""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class McpFeatureCapabilities(DynamicBaseModel):
    """Dynamic capabilities for an MCP feature."""


class McpResourceContent(DynamicBaseModel):
    """Content returned from reading an MCP resource."""
    uri: str = ""
    content: str = ""
    mime_type: str | None = None
    is_binary: bool = False


class McpPromptMessage(DynamicBaseModel):
    """A single message within an MCP prompt result."""
    role: str
    content: str | None = None
    content_type: str | None = None
    mime_type: str | None = None
    resource_uri: str | None = None


class McpPromptResult(DynamicBaseModel):
    """Result of getting a rendered MCP prompt."""
    name: str = ""
    description: str | None = None
    messages: list[McpPromptMessage] = Field(default_factory=list)
