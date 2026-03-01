import asyncio
import os
import subprocess

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.context.manager import ContextManager
from app.core.memory import memory_manager
from app.core.tools import evoloop_tool, get_working_directory
from app.i18n.service import i18n
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.factory import LLMFactory
from app.logging import logger
from app.utils.git import git_command


class Concept(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of what it is and how it is used in this project")
    related_files: list[str] = Field(description="List of file paths related to this concept", default_factory=list)


class ExtractionResult(BaseModel):
    concepts: list[Concept] = Field(description="List of extracted concepts")


HARVEST_PROMPT = """You are a Knowledge Engineer.
Analyze the following code changes (git diff) and extract new "Domain Concepts", "Architecture Patterns", or "Important Decisions".

Criteria for a Concept:
- It is a specific term, class, module, or pattern used in the code.
- It is NOT a generic programming term (like "function", "array") unless used in a specific way.
- It is worth remembering for future tasks (e.g. "PaymentGateway" logic, "RetryPolicy" configuration).

Diff:
{diff}

Extract up to 5 most important concepts.
Output a JSON object.
"""


@evoloop_tool
async def auto_harvest_from_git():
    """
    Analyze uncommitted changes (working directory) to extract and save new Knowledge Concepts.
    Now offloaded to a background Celery task to prevent blocking the agent execution.
    """
    from app.core.engine.tasks import git_harvest_task
    
    ctx = ContextManager.current()
    project_id = ctx.project_id or 1
    cwd = ctx.working_directory or os.getcwd()

    # 0. Check if Git repo exists (Fast check)
    git_dir = os.path.join(cwd, ".git")
    if not os.path.exists(git_dir):
        return i18n.get("prompts.domain_tools.learner.no_git")

    # Dispatch to Celery
    git_harvest_task.delay(cwd, project_id)

    return "Knowledge harvesting initiated in background. I will continue learning from your changes."


async def _run_git(args: list[str], config: RunnableConfig | None = None) -> str:
    cwd = get_working_directory(config)

    # Use util wrapper in a thread pool to avoid blocking the event loop
    res = await asyncio.to_thread(git_command, args, cwd=cwd)

    if res.success:
        return res.stdout
    return f"Error: Git command failed. {res.stderr}"


@evoloop_tool(is_pollable=True)
async def git_status(config: RunnableConfig) -> str:
    """
    Get the current git status (branch, modified files).
    """
    return await _run_git(["status"], config)


@evoloop_tool(is_pollable=True)
async def git_diff(config: RunnableConfig) -> str:
    """
    Show changes between working tree and index (or last commit).
    Useful to verify what you have edited before committing.
    """
    return await _run_git(["diff"], config)


@evoloop_tool(is_state_mutating=True)
async def git_commit(message: str, add_all: bool = True, config: RunnableConfig = None) -> str:
    """
    Commit changes to the repository.

    Args:
        message: Commit message.
        add_all: If True (default), runs 'git add .' before committing.
    """
    if add_all:
        add_res = await _run_git(["add", "."], config)
        if "Error" in add_res:
            return f"Failed to add files: {add_res}"

    return await _run_git(["commit", "-m", message], config)


@evoloop_tool(is_pollable=True)
async def git_history(limit: int = 5, config: RunnableConfig = None) -> str:
    """
    Show the commit log.
    """
    return await _run_git(["log", f"-n {limit}", "--pretty=format:'%h - %an, %ar : %s'"], config)


@evoloop_tool(is_state_mutating=True)
async def git_create_branch(branch_name: str, config: RunnableConfig) -> str:
    """
    Create and checkout a new branch.
    """
    return await _run_git(["checkout", "-b", branch_name], config)
