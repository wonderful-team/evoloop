
from langchain_core.tools import BaseTool

from app.core.tools.registry_utils import AutoDiscoveryRegistry
from app.domain.tools.runtime_registry import get_runtime_tools
from app.infrastructure.mcp.client import mcp_client_manager

# Initialize Registry
REGISTRY = AutoDiscoveryRegistry()

# Scan the entire domain tools package
# This will find any function decorated with @evoloop_tool in app.domain.tools.**
REGISTRY.scan("app.domain.tools")

# Manual Registration for Domain Tools outside app.domain.tools
from app.domain.codebase.retrieval.tools import query_graph_natural_language, search_codebase
REGISTRY.register(query_graph_natural_language)
REGISTRY.register(search_codebase) # Ensure this is registered too if not already


def get_all_tools() -> list[BaseTool]:
    """
    Return a list of all available tools in the domain.
    """
    # Combine discovered tools with dynamic ones (MCP, Runtime)
    return REGISTRY.get_all_tools() + mcp_client_manager.get_tools() + get_runtime_tools()


def get_tools_by_names(names: list[str]) -> list[BaseTool]:
    """
    Dynamically retrieve tools by their string names.
    """
    all_tools = get_all_tools()
    tool_map = {t.name: t for t in all_tools}

    selected_tools = []
    for name in names:
        if name in tool_map:
            selected_tools.append(tool_map[name])
        else:
            # Fallback for MCP tools or specialized mapping if needed
            pass

    return selected_tools


def get_coder_tools() -> list[BaseTool]:
    """
    Return standard tools for the Coder agent.
    """
    # We define the *names* of the tools needed, decoupling from import paths
    tool_names = [
        "consult_architecture",
        "manage_file",
        "explore_codebase",
        "manage_git",
        "manage_memory",
        "consult_lsp",
        "run_command",
        "query_graph_natural_language"
    ]
    return get_tools_by_names(tool_names) + mcp_client_manager.get_tools()


def get_supervisor_tools() -> list[BaseTool]:
    """
    Return tools for the Supervisor agent.
    
    NOTE: Supervisor is a COORDINATOR, not an executor.
    It should NOT have business tools like manage_file or create_plan.
    Those belong to specialized nodes (Coder, Documenter, Planner).
    """
    tool_names = [
        "save_preference",  # Learning user preferences
        "search_concepts",  # Semantic search (read-only)
        "request_human_input",  # HITL - pause for user input
        "analyze_image",  # Vision Perception
        "manage_todo",  # User Todo/Reminders
    ]
    return get_tools_by_names(tool_names)
