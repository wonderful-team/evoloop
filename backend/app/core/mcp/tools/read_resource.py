"""Tool for reading MCP resources."""

import logging

from pydantic import BaseModel, Field

from app.core.mcp import mcp_client_manager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class ReadMcpResourceInput(BaseModel):
    """Input schema for read_mcp_resource tool."""
    server_name: str = Field(
        description="The name of the MCP server hosting the resource."
    )
    uri: str = Field(
        description="The resource URI to read (e.g., 'file:///path/to/file', 'db://table/record')."
    )


@evoloop_tool(
    "read_mcp_resource",
    args_schema=ReadMcpResourceInput,
    is_state_mutating=False,
    summary_template="database_logger.tool_summary.read_mcp_resource"
)
async def read_mcp_resource(server_name: str, uri: str) -> str:
    """
    Read content from an MCP resource URI.
    
    Resources are data sources exposed by MCP servers (files, database records, etc).
    Use list_mcp_resources first to discover available URIs.
    
    The content is returned as text when possible, or base64-encoded if binary.
    """
    try:
        # Ensure connected
        connected = await mcp_client_manager.ensure_connected(server_name)
        if not connected:
            return f"Error: MCP server '{server_name}' is not connected. Please call use_mcp_server('{server_name}') first."

        # Read resource
        result = await mcp_client_manager.read_resource(server_name, uri)

        content = result.get("content", "")
        mime_type = result.get("mime_type", "unknown")
        is_binary = result.get("is_binary", False)

        # Format output
        lines = [
            f"# Resource: {uri}",
            f"**MIME Type:** {mime_type}",
            "",
        ]

        if is_binary:
            lines.append("*Binary content (base64-encoded)*")
            lines.append(content[:500] + "..." if len(content) > 500 else content)
        else:
            lines.append(content)

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error reading MCP resource: {e}")
        return f"Error reading resource '{uri}' from '{server_name}': {str(e)}"
