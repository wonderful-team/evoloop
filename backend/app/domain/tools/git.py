
import subprocess
import os
from langchain_core.tools import tool
from app.logging import get_context

from app.utils.git import git_command

def _run_git(args: list[str]) -> str:
    ctx = get_context()
    cwd = ctx.get("working_directory") or os.getcwd()
    
    # Use util wrapper
    res = git_command(args, cwd=cwd)
    if res.success:
        return res.stdout
    return f"Git Error: {res.stderr}"

@tool
def git_status() -> str:
    """
    Get the current git status (branch, modified files).
    """
    return _run_git(["status"])

@tool
def git_diff() -> str:
    """
    Show changes between working tree and index (or last commit).
    Useful to verify what you have edited before committing.
    """
    return _run_git(["diff"])

@tool
def git_commit(message: str, add_all: bool = True) -> str:
    """
    Commit changes to the repository.
    
    Args:
        message: Commit message.
        add_all: If True (default), runs 'git add .' before committing.
    """
    if add_all:
        add_res = _run_git(["add", "."])
        if "Error" in add_res:
             return f"Failed to add files: {add_res}"
             
    return _run_git(["commit", "-m", message])

@tool
def git_history(limit: int = 5) -> str:
    """
    Show the commit log.
    """
    return _run_git(["log", f"-n {limit}", "--pretty=format:'%h - %an, %ar : %s'"])

@tool
def git_create_branch(branch_name: str) -> str:
    """
    Create and checkout a new branch.
    """
    return _run_git(["checkout", "-b", branch_name])
