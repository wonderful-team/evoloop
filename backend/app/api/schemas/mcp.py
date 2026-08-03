"""API schemas for mcp routes."""

from app.api.schemas.responses import BaseAPIResponse


class McpOperationResponse(BaseAPIResponse):
    """Response for MCP add/remove operations."""

    status: str


class McpConnectResponse(BaseAPIResponse):
    """Response for MCP connect operation."""

    status: str
    name: str
    tools_count: int
