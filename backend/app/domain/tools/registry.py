from typing import List

from langchain_core.tools import BaseTool

from app.domain.tools.facades import manage_file, explore_codebase, manage_git, manage_memory, consult_architecture

from app.infrastructure.mcp.client import mcp_client_manager
from app.domain.tools.execution import run_command
from app.domain.tools.project_tools import create_project_task

# Agent Tools
from app.domain.tools.browser import browser_agent
from app.domain.tools.crawler import crawler_tool
from app.domain.tools.computer import computer_agent_tool
from app.domain.tools.mobile import mobile_agent_tool
from app.domain.tools.memory import save_preference, search_concepts
from app.domain.tools.memory import save_preference, search_concepts
from app.domain.planning.tools import create_plan, update_step_status, analyze_feasibility
from app.domain.tools.learner import harvest_knowledge
# State Tools
from app.domain.tools.state_tools import update_scratchpad

# Vision Tools (Phase 0.1)
from app.domain.tools.vision import analyze_screenshot, locate_element, compare_screenshots, extract_text_from_image

# Human-in-Loop Tools (Phase 0.2)
from app.domain.tools.human_input import request_human_input, request_approval

# Runtime Registry for Dynamic Tools (Phase 9)
from app.domain.tools.dynamic import create_python_tool

# Runtime Registry (Isolated)
from app.domain.tools.runtime_registry import get_runtime_tools


def get_all_tools() -> List[BaseTool]:
    """
    Return a list of all available tools in the domain.
    """
    # Lazy import to avoid circular dependency
    from app.core.orchestration.delegator import delegate_task

    return [
        # Match previous list...
        # Core 4 Facades
        manage_file,
        explore_codebase,
        manage_git,
        manage_memory,
        
        # Primary Visualization
        consult_architecture,
        
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
        create_plan, update_step_status, analyze_feasibility,
        
        # Learning
        harvest_knowledge,
        
        # State
        update_scratchpad,

        # Dynamic Tooling (Meta-Tool)
        create_python_tool,
        
        # Vision (Phase 0.1)
        analyze_screenshot,
        locate_element,
        compare_screenshots,
        extract_text_from_image,
        
        # Human-in-Loop (Phase 0.2)
        request_human_input,
        request_approval,
        
        # Orchestration (Phase 10)
        delegate_task

    ] + mcp_client_manager.get_tools() + get_runtime_tools()

def get_coder_tools() -> List[BaseTool]:
    """
    Return standard tools for the Coder agent.
    Includes Architect Mode tools.
    """
    core_tools = [
        consult_architecture, # [ARCHITECT MODE]
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
    ]
    return core_tools


def get_tools_by_names(names: List[str]) -> List[BaseTool]:
    """
    Dynamically retrieve tools by their string names.
    Useful for Universal Agent configuration.
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
