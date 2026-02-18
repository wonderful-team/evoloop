"""
L2 Dynamic Tool Request — Phase Progressive Disclosure.

Allows the Agent to request tools that are not in its current working set.
The tool performs semantic search across the full tool pool (registry + MCP)
and returns matching tools' descriptions without injecting them automatically.
"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def request_tool(capability: str) -> str:
    """
    Request access to a tool that is not currently available in your working set.
    Describe the capability you need (e.g. "send email", "query database", "web search").
    Returns descriptions of matching tools if found, or instructions if the capability
    requires connecting to an external service.
    
    Args:
        capability: Natural language description of the needed capability.
    """
    from app.domain.tools.retrieval import tool_retriever
    from app.core.tools.registry_utils import _build_static_tool_map

    results = []

    # 1. Search the semantic tool index (PG-backed)
    try:
        matched_tools = await tool_retriever.retrieve(capability, k=5)
        if matched_tools:
            for t in matched_tools:
                results.append(f"- **{t.name}**: {t.description}")
    except Exception as e:
        logger.warning(f"Semantic tool search failed: {e}")

    # 2. If no hits from semantic index, check static registry
    if not results:
        static_map = _build_static_tool_map()
        capability_lower = capability.lower()
        for name, t in static_map.items():
            desc = (t.description or "").lower()
            if any(kw in desc or kw in name for kw in capability_lower.split()):
                results.append(f"- **{name}**: {t.description}")
        if len(results) > 5:
            results = results[:5]

    # 3. Check MCP tools
    try:
        from app.infrastructure.mcp.client import mcp_client_manager
        for t in mcp_client_manager.get_tools():
            desc = (t.description or "").lower()
            if any(kw in desc or kw in t.name for kw in capability.lower().split()):
                results.append(f"- **{t.name}** (MCP): {t.description}")
    except Exception:
        pass

    if results:
        tool_list = "\n".join(results[:8])
        return (
            f"Found {len(results)} potentially matching tools for '{capability}':\n\n"
            f"{tool_list}\n\n"
            f"Note: These tools are available in the system but may not be in your "
            f"current working set. Ask the Supervisor to assign them if needed."
        )
    else:
        return (
            f"No tools found matching '{capability}'. "
            f"This capability may require:\n"
            f"1. Connecting a new MCP server that provides this functionality\n"
            f"2. Implementing a new tool in the domain layer\n"
            f"3. Using existing tools creatively to achieve the goal"
        )
