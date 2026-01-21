from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.tools import get_working_directory
from app.utils.git import git_command


def _run_git(args: list[str], config: RunnableConfig | None = None) -> str:
    cwd = get_working_directory(config)

    # Use util wrapper
    res = git_command(args, cwd=cwd)
    if res.success:
        return res.stdout
    return f"Git Error: {res.stderr}"


@tool
def git_status(config: RunnableConfig) -> str:
    """
    Get the current git status (branch, modified files).
    """
    return _run_git(["status"], config)


@tool
def git_diff(config: RunnableConfig) -> str:
    """
    Show changes between working tree and index (or last commit).
    Useful to verify what you have edited before committing.
    """
    return _run_git(["diff"], config)


@tool
def git_commit(message: str, add_all: bool = True, config: RunnableConfig = None) -> str:
    """
    Commit changes to the repository.

    Args:
        message: Commit message.
        add_all: If True (default), runs 'git add .' before committing.
    """
    if add_all:
        add_res = _run_git(["add", "."], config)
        if "Error" in add_res:
            return f"Failed to add files: {add_res}"

    return _run_git(["commit", "-m", message], config)


@tool
def git_history(limit: int = 5, config: RunnableConfig = None) -> str:
    """
    Show the commit log.
    """
    return _run_git(["log", f"-n {limit}", "--pretty=format:'%h - %an, %ar : %s'"], config)

@tool
def git_create_branch(branch_name: str, config: RunnableConfig) -> str:
    """
    Create and checkout a new branch.
    """
    return _run_git(["checkout", "-b", branch_name], config)
