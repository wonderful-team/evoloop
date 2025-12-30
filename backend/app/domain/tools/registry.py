from typing import List

from langchain_core.tools import BaseTool

from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.planning.tools import analyze_feasibility
from app.domain.tools.browser import browser_agent
from app.domain.tools.computer import computer_agent_tool
from app.domain.tools.crawler import crawler_tool  # New Tool
from app.domain.tools.document_reader import read_document
from app.domain.tools.mobile import mobile_agent_tool
from app.domain.tools.project_tools import create_project_task
from app.domain.tools.visualizer import get_annotated_tree
from app.infrastructure.filesystem.tool import list_files, read_file, grep_files, write_file_content, edit_file
from app.infrastructure.mcp.client import mcp_client_manager
from app.domain.tools.git import git_status, git_diff, git_commit, git_history, git_create_branch


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
        edit_file,
        run_shell_command,
        search_codebase,
        get_annotated_tree,
        read_document,
        analyze_feasibility,
        save_preference,
        get_user_preferences,
        search_concepts,
        add_concept,
        # Git Tools
        git_status,
        git_diff,
        git_commit,
        git_history,
        git_create_branch,
        # Agents
        browser_agent,
        crawler_tool,
        computer_agent_tool,
        mobile_agent_tool,
        # Project Management
        create_project_task
    ] + mcp_client_manager.get_tools()
