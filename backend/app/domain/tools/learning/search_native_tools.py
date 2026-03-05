from typing import Any

from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool


class SearchNativeToolsSchema(BaseModel):
    query: str = Field(
        "",
        description="Optional keyword to filter tools by name or description. Leave empty to list all available execution tools.",
    )


@evoloop_tool(is_pollable=True)
async def search_native_tools(query: str = "") -> dict[str, Any]:
    """
    Yellow Pages directory for Native Python and MCP Tools. 
    Use this to look up available system capabilities (like executing commands, controlling environment) before attempting to invent tools.
    Returns a list of matching tools with their descriptions and arguments.
    """
    from app.core.tools.manager import tool_manager
    from app.core.tools.registry import get_tool_to_nodes_mapping, clear_registry_cache

    # Ensure registry cache is clear to see all discovered tools
    clear_registry_cache()

    all_tools = tool_manager.get_all_capabilities()
    tool_to_nodes = get_tool_to_nodes_mapping()

    results = []

    query_lower = query.lower() if query else ""

    for tool in all_tools:
        # Avoid including self in the response to save tokens if we want, or just include it.
        name = tool.name
        desc = tool.description or ""

        if query_lower:
            if query_lower not in name.lower() and query_lower not in desc.lower():
                continue

        # Extract arguments schema
        args_schema = {}
        if hasattr(tool, "args_schema") and tool.args_schema:
            try:
                for fname, finfo in tool.args_schema.model_fields.items():
                    args_schema[fname] = {
                        "type": str(finfo.annotation),
                        "description": finfo.description or ""
                    }
            except Exception:
                pass

        # Determine route_to
        # If it's a native tool, we use the YAML mapping.
        # If it's an MCP tool, it's virtually always handled by the 'worker' node in our current architecture.
        route_to = tool_to_nodes.get(name, [])
        if not route_to and name.startswith("mcp__"):
            route_to = ["worker"]

        results.append({
            "name": name,
            "description": desc,
            "route_to": route_to,
            "arguments": args_schema
        })

    if not results:
        return {
            "result_type": "no_match",
            "instruction": f"No native or MCP tools found matching '{query}'. Try a broader query or empty string to see all tools."
        }

    return {
        "result_type": "success",
        "total_tools_matched": len(results),
        "tools": results,
        "instruction": "These are the built-in system tools. You may instruct downstream nodes (like worker) to use them in the `agent_config.tools` array of the Execution Ticket."
    }
