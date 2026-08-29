from app.core.tools import evoloop_tool


@evoloop_tool(
    is_hidden=True, summary_template="evoloop.tool_summary.search_native_tools"
)
async def search_native_tools(query: str = "") -> str:
    """
    Search available system tools and capabilities.
    Use this to find specific 'sensors' (telemetry) or 'actuators' (control tools).
    Returns tools grouped by ecosystem for better strategic planning.
    """
    from app.core.tools.manager import tool_manager

    all_tools = await tool_manager.get_all_capabilities()

    query_lower = query.lower() if query else ""

    # Ecosystem buckets
    groups = {"android": [], "macos": [], "web": [], "universal": []}

    for tool in all_tools:
        name = tool.name
        desc = tool.description or ""

        if (
            query_lower
            and query_lower not in name.lower()
            and query_lower not in desc.lower()
        ):
            continue

        # Simple prefix-based ecosystem detection
        eco = "universal"
        if any(prefix in name for prefix in ["adb_", "mobile_"]):
            eco = "android"
        elif any(
            prefix in name
            for prefix in ["macos_", "applescript_", "click_at", "type_text"]
        ):
            eco = "macos"
        elif any(prefix in name for prefix in ["browser_", "read_url"]):
            eco = "web"

        groups[eco].append(
            {
                "name": name,
                "description": desc,
            }
        )

    # 构建纯文本输出（Agent 得到的是文本，不是 dict/JSON）
    lines = []
    for eco, tools in groups.items():
        if not tools:
            continue
        lines.append(f"\n## {eco.upper()} ({len(tools)} tools)")
        for t in tools:
            lines.append(f"- {t['name']}: {t['description']}")

    total_count = sum(len(t) for t in groups.values())
    return "\n".join(lines) if lines else "No tools found.", {"count": total_count}
