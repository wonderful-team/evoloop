import logging

from pydantic import BaseModel, Field

from app.core.mcp import mcp_client_manager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class UseMcpServerSchema(BaseModel):
    server_name: str = Field(description="The name of the MCP server to activate (e.g., 'github', 'postgres').")


@evoloop_tool(
    "use_mcp_server",
    args_schema=UseMcpServerSchema,
    is_state_mutating=True,
    is_hidden=True,
    summary_template="database_logger.tool_summary.use_mcp",
    name_map={"zh": "使用MCP服务器", "en": "Use MCP Server"}
)
async def use_mcp_server(server_name: str) -> str:
    """
    Activates an external MCP server to load its specialized tools into your current session.
    Use this when you need capabilities listed in the MCP EXTERNAL CAPABILITIES directory but do not currently have the tools available.
    After calling this, the required tools will be injected into your prompt on the next turn.

    In the EvoLoop architecture, this tool is intercepted by the engine or simply
    returns instructions to the LLM to proceed, while state modifications happen
    via a state update trick if needed, or by simply returning a message.
    """
    try:
        # Check if server exists
        servers = await mcp_client_manager.list_servers()
        server_exists = any(s["name"] == server_name for s in servers)

        if not server_exists:
            return f"Error: MCP server '{server_name}' is not configured or does not exist."

        # Ensure connected
        connected = await mcp_client_manager.ensure_connected(server_name)
        if not connected:
            return f"Error: Failed to connect to MCP server '{server_name}'."

        tools = await mcp_client_manager.get_tools(server_name)
        tool_names = [t.name for t in tools]

        # We need to tell the LLM that the tools are available, BUT the LLM's current
        # Runnable loop won't have the tools injected until the Operator node restarts or
        # the AgentEngine rebinds.
        # Actually, if we return this string, the LLM will try to use the tools on the NEXT
        # step in the same AgentEngine loop, which will FAIL because the tools list was bound
        # at `AgentEngine.run_node` startup.
        # To fix this, we return a special directive that forces the LLM to end its turn.

        return (
            f"Successfully connected to MCP Server '{server_name}'. "
            f"Tools available: {', '.join(tool_names)}.\n"
            "CRITICAL: The tools are NOT injected yet. You MUST stop generating and yield control back to the system. "
            "Simply reply with: 'I have requested the MCP server. I am now waiting for the system to reload with the new tools.' "
            "Do NOT attempt to use the new tools in this exact message."
        )
    except Exception as e:
        logger.error(f"Error in use_mcp_server: {e}")
        return f"Error activating MCP server: {str(e)}"
