"""MCP client schemas."""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class McpResource(DynamicBaseModel):
    uri: str
    name: str
    mimeType: str | None = None
    description: str | None = None


class McpPromptArgument(DynamicBaseModel):
    name: str
    required: bool = False


class McpPrompt(DynamicBaseModel):
    name: str
    description: str | None = None
    arguments: list[McpPromptArgument] = Field(default_factory=list)


class McpServerSummary(DynamicBaseModel):
    name: str
    command: str | None = None
    transport: str | None = None
    status: str
    tools_count: int
    enabled: bool
