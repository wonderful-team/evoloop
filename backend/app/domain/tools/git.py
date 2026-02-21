import os
import subprocess

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.memory import memory_manager
from app.core.tools import evoloop_tool, get_working_directory
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.factory import LLMFactory
from app.i18n.service import i18n
from app.logging import logger
from app.core.context.manager import ContextManager
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
    Call this at the end of a task to 'learn' from the work done.

    Works with both staged and unstaged changes in the working directory.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id or 1
    cwd = ctx.working_directory or os.getcwd()

    # 0. Check if Git repo exists
    git_dir = os.path.join(cwd, ".git")
    if not os.path.exists(git_dir):
        return i18n.get("prompts.domain_tools.learner.no_git")

    # 1. Get Git Diff (working directory vs HEAD)
    try:
        # Compare working directory against HEAD (captures uncommitted changes)
        cmd = ["git", "diff", "HEAD"]
        process = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
        diff_text = process.stdout

        if not diff_text.strip():
            return i18n.get("prompts.domain_tools.learner.no_changes")

        # Limit diff size to avoid context overflow
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...(truncated)"

    except subprocess.TimeoutExpired:
        return i18n.get("prompts.domain_tools.learner.git_timeout")
    except Exception as e:
        return i18n.get("prompts.domain_tools.learner.git_error", error=str(e))

    # 2. Extract Concepts using LLM
    llm = LLMFactory.create_llm()
    structured_llm = llm.with_structured_output(ExtractionResult)
    user_lang = SystemConfigService.get_language_preference()

    lang_directive = f"\n\nLANGUAGE PROTOCOL:\nUser Language: {user_lang}\nConcept 'description' fields MUST be written in {user_lang}.\nConcept 'name' should usually remain in English (Code)."

    try:
        result = await structured_llm.ainvoke([
            SystemMessage(content=HARVEST_PROMPT.format(diff=diff_text) + lang_directive)
        ], config={"callbacks": []})
    except Exception as e:
        logger.error(f"Harvest extraction failed: {e}")
        return i18n.get("prompts.domain_tools.learner.extract_error", error=str(e))

    # 3. Save to Memory
    saved_count = 0
    response_lines = [i18n.get("prompts.domain_tools.learner.harvested_header")]

    if result and result.concepts:
        for concept in result.concepts:
            # Add to Neo4j
            from app.core.memory.interfaces.long_term import Concept as MemConcept
            mem_concept = MemConcept(concept.name, concept.description, project_id, concept.related_files)
            await memory_manager.long_term.store_concept(mem_concept)
            saved_count += 1
            response_lines.append(f"- {concept.name}")

    if saved_count == 0:
        return i18n.get("prompts.domain_tools.learner.no_concepts")

    return "\n".join(response_lines)


def _run_git(args: list[str], config: RunnableConfig | None = None) -> str:
    cwd = get_working_directory(config)

    # Use util wrapper
    res = git_command(args, cwd=cwd)
    if res.success:
        return res.stdout
    return f"Error: Git command failed. {res.stderr}"


@evoloop_tool
def git_status(config: RunnableConfig) -> str:
    """
    Get the current git status (branch, modified files).
    """
    return _run_git(["status"], config)


@evoloop_tool
def git_diff(config: RunnableConfig) -> str:
    """
    Show changes between working tree and index (or last commit).
    Useful to verify what you have edited before committing.
    """
    return _run_git(["diff"], config)


@evoloop_tool
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


@evoloop_tool
def git_history(limit: int = 5, config: RunnableConfig = None) -> str:
    """
    Show the commit log.
    """
    return _run_git(["log", f"-n {limit}", "--pretty=format:'%h - %an, %ar : %s'"], config)


@evoloop_tool
def git_create_branch(branch_name: str, config: RunnableConfig) -> str:
    """
    Create and checkout a new branch.
    """
    return _run_git(["checkout", "-b", branch_name], config)
