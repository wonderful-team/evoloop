from typing import List
from langchain_core.tools import BaseTool
from app.infrastructure.mcp.client import mcp_client_manager

from app.infrastructure.filesystem.tool import list_files, read_file, grep_files, write_file_content
from app.domain.tools.execution import run_shell_command
from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.tools.document_reader import read_document
from app.domain.planning.tools import analyze_feasibility, create_plan, update_step_status
from app.domain.tools.visualizer import get_annotated_tree
from app.domain.tools.memory import save_preference, get_user_preferences, search_concepts, add_concept
from app.domain.tools.browser import browser_agent
from app.domain.tools.project_tools import decompose_requirements, create_project_task_async
# Add other tools as needed


def get_all_tools() -> List[BaseTool]:
    """
    Return a list of all available tools in the domain.
    """
    return [
        list_files,
        read_file,
        grep_files,
        write_file_content,
        run_shell_command,
        search_codebase,
        get_annotated_tree,
        read_document,
        analyze_feasibility,
        save_preference,
        get_user_preferences,
        search_concepts,
        add_concept,
        browser_agent,
        # Project Management
        decompose_requirements,
        create_project_task_async
    ] + mcp_client_manager.get_tools()
