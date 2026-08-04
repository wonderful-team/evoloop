"""Tool for listing MCP resources."""

import logging

from pydantic import BaseModel, Field

from app.core.mcp import mcp_client_manager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class ListMcpResourcesInput(BaseModel):
    """Input schema for list_mcp_resources tool."""

    server_name: str = Field(
        description="The name of the MCP server to list resources from (e.g., 'github', 'postgres')."
    )


@evoloop_tool(
    "list_mcp_resources",
    args_schema=ListMcpResourcesInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.list_mcp_resources",
)
async def list_mcp_resources(server_name: str) -> str:
    """
    List all available resources from an MCP server.

    Resources are files, database records, or other data sources exposed by the MCP server
    that can be read using the read_mcp_resource tool.

    Use this to discover what resources are available before trying to read them.
    """
    try:
        # Ensure connected
        connected = await mcp_client_manager.ensure_connected(server_name)
        if not connected:
            return f"Error: MCP server '{server_name}' is not connected. Please call use_mcp_server('{server_name}') first."

        # Get formatted list
        output = mcp_client_manager.get_resources_formatted(server_name)

        if not output or output == "*No resources available on this server.*":
            return f"MCP server '{server_name}' is connected but has no resources available."

        return output

    except Exception as e:
        logger.error(f"Error listing MCP resources: {e}")
        return f"Error listing resources from '{server_name}': {str(e)}"
