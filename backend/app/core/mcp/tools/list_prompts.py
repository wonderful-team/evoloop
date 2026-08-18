"""Tool for listing MCP prompts."""

import logging

from pydantic import BaseModel, Field

from app.core.mcp import mcp_client_manager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class ListMcpPromptsInput(BaseModel):
    """Input schema for list_mcp_prompts tool."""

    server_name: str = Field(
        description="The name of the MCP server to list prompts from (e.g., 'github', 'postgres')."
    )


@evoloop_tool(
    "list_mcp_prompts",
    args_schema=ListMcpPromptsInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.list_mcp_prompts",
)
async def list_mcp_prompts(server_name: str) -> str:
    """
    List all available prompt templates from an MCP server.

    Prompts are reusable templates that can be rendered with arguments.
    They are useful for standardized interactions with the MCP server.

    Use this to discover what prompts are available before using get_mcp_prompt.
    """
    try:
        # Ensure connected
        connected = await mcp_client_manager.ensure_connected(server_name)
        if not connected:
            return f"Error: MCP server '{server_name}' is not connected. Please call use_mcp_server('{server_name}') first."

        # Get formatted list
        output = mcp_client_manager.get_prompts_formatted(server_name)

        if not output or output == "*No prompts available on this server.*":
            return f"MCP server '{server_name}' is connected but has no prompts available."

        return output

    except Exception as e:
        logger.exception(f"Error listing MCP prompts: {e}")
        return f"Error listing prompts from '{server_name}': {str(e)}"
