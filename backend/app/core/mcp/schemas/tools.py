"""MCP tool input schemas."""

from app.infrastructure.pydantic_base import DynamicBaseModel


class UseMcpServerSchema(DynamicBaseModel):
    """Schema for use_mcp_server tool."""
    server_name: str
    tool_name: str
    arguments: dict | None = None


class GetMcpPromptInput(DynamicBaseModel):
    server_name: str
    prompt_name: str
    arguments: dict | None = None


class ListMcpPromptsInput(DynamicBaseModel):
    server_name: str


class ReadMcpResourceInput(DynamicBaseModel):
    server_name: str
    uri: str


class ListMcpResourcesInput(DynamicBaseModel):
    server_name: str
