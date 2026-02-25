from typing import Any

from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool


class SearchNativeToolsSchema(BaseModel):
    query: str = Field(
        "",
        description="Optional keyword to filter tools by name or description. Leave empty to list all available execution tools.",
    )


@evoloop_tool
async def search_native_tools(query: str = "") -> dict[str, Any]:
    """
    Yellow Pages directory for Native Python and MCP Tools. 
    Use this to look up available system capabilities (like executing commands, controlling environment) before attempting to invent tools.
    Returns a list of matching tools with their descriptions and arguments.
    """
    from app.core.tools.manager import tool_manager
    all_tools = tool_manager.get_all_capabilities()

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

        results.append({
            "name": name,
            "description": desc,
            "arguments": args_schema
        })

    if not results:
        return {
            "result_type": "no_match",
            "instruction": f"No native tools found matching '{query}'. Try a broader query or empty string to see all tools."
        }

    return {
        "result_type": "success",
        "total_tools_matched": len(results),
        "tools": results,
        "instruction": "These are the built-in system tools. You may instruct downstream nodes (like worker) to use them in the `agent_config.tools` array of the Execution Ticket."
    }
