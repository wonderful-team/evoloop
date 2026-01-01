from typing import List

from langchain_core.tools import BaseTool

from app.domain.tools.facades import manage_file, explore_codebase, manage_git, manage_memory
from app.infrastructure.mcp.client import mcp_client_manager
from app.domain.tools.execution import run_command
from app.domain.tools.project_tools import create_project_task
from app.domain.tools.visualizer import get_annotated_tree

# Agent Tools
from app.domain.tools.browser import browser_agent
from app.domain.tools.crawler import crawler_tool
from app.domain.tools.computer import computer_agent_tool
from app.domain.tools.mobile import mobile_agent_tool
from app.domain.tools.memory import save_preference, search_concepts
from app.domain.planning.tools import create_plan, update_step_status, analyze_feasibility

def get_all_tools() -> List[BaseTool]:
    """
    Return a list of all available tools in the domain.
    """
    return [
        # Core 4 Facades
        manage_file,
        explore_codebase,
        manage_git,
        manage_memory,
        
        # Primary Visualization
        get_annotated_tree,
        
        # Execution
        run_command,
        
        # Agents
        browser_agent,
        crawler_tool,
        computer_agent_tool,
        mobile_agent_tool,
        
        # Project Management
        create_project_task,
        
        # Planning & Memory
        save_preference, search_concepts,
        create_plan, update_step_status, analyze_feasibility

    ] + mcp_client_manager.get_tools()

def get_coder_tools() -> List[BaseTool]:
    """
    Return standard tools for the Coder agent.
    """
    core_tools = [
        get_annotated_tree,
        manage_file,
        explore_codebase,
        manage_git,
        manage_memory,
        run_command,
    ]
    return core_tools + mcp_client_manager.get_tools()

def get_supervisor_tools() -> List[BaseTool]:
    """
    Return tools for the Supervisor agent.
    """
    core_tools = [
        manage_file, 
        save_preference, 
        search_concepts, 
        create_plan, 
        update_step_status, 
        analyze_feasibility
    ]
    return core_tools
