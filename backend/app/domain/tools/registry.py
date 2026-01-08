from typing import List
from langchain_core.tools import BaseTool
from app.core.tools.registry_utils import AutoDiscoveryRegistry
from app.infrastructure.mcp.client import mcp_client_manager
from app.domain.tools.runtime_registry import get_runtime_tools

# Initialize Registry
REGISTRY = AutoDiscoveryRegistry()

# Scan the entire domain tools package
# This will find any function decorated with @evoloop_tool in app.domain.tools.**
REGISTRY.scan("app.domain.tools")

def get_all_tools() -> List[BaseTool]:
    """
    Return a list of all available tools in the domain.
    """
    # Combine discovered tools with dynamic ones (MCP, Runtime)
    return REGISTRY.get_all_tools() + mcp_client_manager.get_tools() + get_runtime_tools()

def get_tools_by_names(names: List[str]) -> List[BaseTool]:
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

def get_coder_tools() -> List[BaseTool]:
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
        "run_command"
    ]
    return get_tools_by_names(tool_names) + mcp_client_manager.get_tools()

def get_supervisor_tools() -> List[BaseTool]:
    """
    Return tools for the Supervisor agent.
    """
    tool_names = [
        "manage_file", 
        "save_preference", 
        "search_concepts", 
        "create_plan",
        "delegate_task" # Supervisor needs delegation
    ]
    return get_tools_by_names(tool_names)
