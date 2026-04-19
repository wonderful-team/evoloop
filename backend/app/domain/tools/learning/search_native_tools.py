from typing import Any

from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool


class SearchNativeToolsSchema(BaseModel):
    query: str = Field(
        "",
        description="Optional keyword to filter tools by name or description. Leave empty to list all available execution tools.",
    )


@evoloop_tool(
    is_pollable=True,
    is_hidden=True,
    name_map={"zh": "搜索原生工具", "en": "Search Native Tools"}
)
async def search_native_tools(query: str = "") -> dict[str, Any]:
    """
    Search available system tools and capabilities. 
    Use this to find specific 'sensors' (telemetry) or 'actuators' (control tools).
    Returns tools grouped by ecosystem for better strategic planning.
    """
    from app.core.tools.manager import tool_manager
    from app.core.tools.registry import clear_registry_cache

    clear_registry_cache()
    all_tools = await tool_manager.get_all_capabilities()

    query_lower = query.lower() if query else ""
    
    # Ecosystem buckets
    groups = {
        "android": [],
        "macos": [],
        "web": [],
        "universal": []
    }

    for tool in all_tools:
        name = getattr(tool, "name", "")
        desc = getattr(tool, "description", "") or ""

        if query_lower and query_lower not in name.lower() and query_lower not in desc.lower():
            continue

        # Simple prefix-based ecosystem detection
        eco = "universal"
        if any(prefix in name for prefix in ["adb_", "mobile_"]):
            eco = "android"
        elif any(prefix in name for prefix in ["macos_", "applescript_", "click_at", "type_text"]):
            eco = "macos"
        elif any(prefix in name for prefix in ["browser_", "read_url"]):
            eco = "web"

        groups[eco].append({
            "name": name,
            "description": desc,
        })

    return {
        "result_type": "success",
        "ecosystems": {k: v for k, v in groups.items() if v},
        "instruction": "Grouped tools by ecosystem. Use specific tools based on your telemetry analysis."
    }
