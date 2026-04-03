"""Tool for getting MCP prompts."""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.mcp import mcp_client_manager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class GetMcpPromptInput(BaseModel):
    """Input schema for get_mcp_prompt tool."""
    server_name: str = Field(
        description="The name of the MCP server hosting the prompt."
    )
    prompt_name: str = Field(
        description="The name of the prompt template to render."
    )
    arguments: str = Field(
        default="{}",
        description='JSON object with arguments for the prompt (e.g., {"pr_number": "123", "repo": "myrepo"}).'
    )


@evoloop_tool(
    "get_mcp_prompt",
    args_schema=GetMcpPromptInput,
    is_state_mutating=False,
    summary_template="database_logger.tool_summary.get_mcp_prompt",
    name_map={"zh": "获取MCP提示词", "en": "Get MCP Prompt"}
)
async def get_mcp_prompt(server_name: str, prompt_name: str, arguments: str = "{}") -> str:
    """
    Get a rendered prompt template from an MCP server.
    
    Prompts are reusable templates that can be filled with arguments.
    Use list_mcp_prompts first to discover available prompts and their required arguments.
    
    The returned prompt can be used directly in your response or processed further.
    """
    try:
        # Parse arguments
        try:
            args_dict = json.loads(arguments) if arguments else {}
            if not isinstance(args_dict, dict):
                return "Error: arguments must be a JSON object (e.g., '{\"key\": \"value\"}')"
        except json.JSONDecodeError as e:
            return f"Error parsing arguments JSON: {e}"
        
        # Ensure connected
        connected = await mcp_client_manager.ensure_connected(server_name)
        if not connected:
            return f"Error: MCP server '{server_name}' is not connected. Please call use_mcp_server('{server_name}') first."
        
        # Get prompt
        result = await mcp_client_manager.get_prompt(server_name, prompt_name, args_dict)
        
        # Format output
        lines = [
            f"# Prompt: {prompt_name}",
        ]
        
        if result.get("description"):
            lines.append(f"*{result['description']}*")
        lines.append("")
        
        # Render messages
        for i, msg in enumerate(result.get("messages", []), 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_type = msg.get("content_type", "text")
            
            lines.append(f"## Message {i} ({role})")
            
            if content_type == "image":
                lines.append("*[Image content]*")
            elif content_type == "resource":
                resource_uri = msg.get("resource_uri", "unknown")
                lines.append(f"*[Resource: {resource_uri}]*")
                lines.append(content)
            else:
                lines.append(content)
            
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting MCP prompt: {e}")
        return f"Error getting prompt '{prompt_name}' from '{server_name}': {str(e)}"
