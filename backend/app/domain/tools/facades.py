import os
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.domain.codebase.analysis.tools import find_definition
from app.domain.codebase.retrieval.tools import search_codebase
from app.core.memory import memory_manager
from app.domain.tools.git import (
    git_commit,
    git_create_branch,
    git_diff,
    git_history,
    git_status,
)

# Import delegated tools
from app.domain.tools.memory import (
    add_concept,
    get_user_preferences,
    save_preference,
    search_concepts,
)
from app.domain.tools.files import edit_file, grep_files
from app.core.context.manager import ContextManager

# ... (Delegate imports removed as they are now in actions)
# Import the new dispatched tool
from app.utils.file import write_file_contents as utils_write_file
from app.constants import ALLOWED_DOC_EXTENSIONS


@evoloop_tool
async def write_document(
    path: str, content: str, config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    [DOCS-ONLY] Write documentation files (.md, .txt, .json, .yaml, .csv) ONLY.
    """
    if not any(path.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
        return f"Error: Permission Denied. You may only write to {ALLOWED_DOC_EXTENSIONS}. For code changes, route to Coder."

    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    utils_write_file(content, target_path)
    return f"Successfully wrote documentation to {path}"


@evoloop_tool
async def edit_document(
    path: str,
    target: str,
    replacement: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    [DOCS-ONLY] Edit documentation files (.md, .txt, .json, .yaml, .csv) ONLY.
    """
    if not any(path.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
        return f"Error: Permission Denied. You may only edit {ALLOWED_DOC_EXTENSIONS}. For code changes, route to Coder."

    # Reuse generic edit tool logic or implement simple replace
    return await edit_file.ainvoke(
        {"path": path, "target": target, "replacement": replacement}, config=config
    )


@evoloop_tool
async def explore_codebase(
    action: Literal["search_symbol", "search_text", "semantic_code_search", "analyze_impact"],
    query: str,
    scope_path: str | None = None,  # Optional file pattern or path
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Unified Codebase Exploration Tool.

    Args:
        action:
            - 'search_symbol': Find definition of class/function (Graph + Fallback).
            - 'search_text': Grep for string literal (Regex).
            - 'semantic_code_search': Semantic search for "How does X work?" (Vector).
            - 'analyze_impact': Find usages/dependants of a symbol (Graph).
        query: The symbol name, regex pattern, or question.
        scope_path: Optional glob pattern or path.
    """
    # ... imports delegated to function scope to avoid circular deps if needed
    from app.domain.codebase.analysis.tools import analyze_impact

    if action == "search_symbol":
        return await find_definition.ainvoke(
            {"symbol_name": query, "file_pattern": scope_path}, config=config
        )

    elif action == "search_text":
        # Delegate to grep
        args = {"pattern": query, "is_regex": True}
        if scope_path:
            args["path"] = scope_path
        return grep_files.invoke(args, config=config)

    elif action == "semantic_code_search":
        return await search_codebase.ainvoke({"query": query}, config=config)

    elif action == "analyze_impact":
        return await analyze_impact.ainvoke({"symbol_name": query}, config=config)

    return f"Error: Unknown action '{action}'"


@evoloop_tool
def manage_git(
    action: Literal["status", "diff", "commit", "log", "create_branch"],
    argument: str | None = None,  # message for commit, branch name, etc.
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Unified Git Operations.

    Args:
        action: Git command.
        argument: Contextual argument (commit message, branch name).
    """
    if action == "status":
        return git_status.invoke({}, config=config)
    elif action == "diff":
        return git_diff.invoke({}, config=config)
    elif action == "commit":
        if not argument:
            return "Error: 'argument' (message) required for commit."
        return git_commit.invoke({"message": argument}, config=config)
    elif action == "log":
        return git_history.invoke({}, config=config)
    elif action == "create_branch":
        if not argument:
            return "Error: 'argument' (branch_name) required."
        return git_create_branch.invoke({"branch_name": argument}, config=config)

    return f"Error: Unknown action '{action}'"


@evoloop_tool
async def manage_memory(
    action: Literal[
        "save_preference",
        "retrieve_preferences",
        "add_concept",
        "search_concepts",
        "find_related_episodes",
    ] = "retrieve_preferences",
    key: str | None = None,  # concept name or pref key
    value: str | None = None,  # description or pref value
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Unified Memory Management.

    Actions:
    - save_preference: Save a user preference (key=name, value=preference)
    - retrieve_preferences: Get all user preferences
    - add_concept: Add a knowledge concept (key=name, value=description)
    - search_concepts: Search for concepts (key=query)
    - find_related_episodes: Find historical tasks related to a concept (key=concept_name)
    """
    # Assuming user_id is handled implicitly or 'user_default'
    user_id = "user_default"

    if action == "save_preference":
        if not key or not value:
            return "Error: key/value required."
        return await save_preference.ainvoke({"key": key, "value": value}, config=config)

    elif action == "retrieve_preferences":
        return await get_user_preferences.ainvoke({"user_id": user_id}, config=config)

    elif action == "add_concept":
        if not key or not value:
            return "Error: key (name) and value (description) required."
        return await add_concept.ainvoke(
            {"name": key, "description": value}, config=config
        )

    elif action == "search_concepts":
        if not key:
            return "Error: key (query) required."
        return await search_concepts.ainvoke({"query": key}, config=config)

    elif action == "find_related_episodes":
        if not key:
            return "Error: key (concept_name) required."
        ctx = ContextManager.current()
        project_id = ctx.project_id or 1
        episodes = await memory_manager.long_term.find_episodes_by_concept(key, project_id)
        if not episodes:
            return f"No historical episodes found related to '{key}'."
        lines = [f"**Historical Tasks Related to '{key}':**"]
        for ep in episodes:
            status = "FAILED" if ep.get("error") else "SUCCESS"
            lines.append(f"- [{status}] {ep.get('goal', 'Unknown')}")
            if ep.get("result"):
                lines.append(f"  Result: {ep.get('result')[:100]}...")
        return "\n".join(lines)

    return f"Error: Unknown action '{action}'"


@evoloop_tool
async def consult_architecture(path: str = ""):
    """
    [ARCHITECT MODE] Consult the system's architectural documentation for a specific directory/module.
    Returns the module's role, sub-modules, and dependencies.
    Use this BEFORE refactoring or adding complex features to understand the ecosystem.

    Args:
        path: The relative path of the directory to inspect (e.g., "backend/app/core"). Defaults to root ("").
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id

    if not project_id:
        return "Error: No active project context."

    info = await memory_manager.graph.get_directory_info(project_id, path)

    output = [f"# Architecture Report: {info['path'] or 'Root'}"]
    output.append(f"**Summary**: {info['summary']}\n")

    if info["sub_modules"]:
        output.append("**Sub-Modules**:")
        for Sub in info["sub_modules"]:
            # Truncate summary for brevity
            s = Sub["summary"] or "No summary"
            output.append(f"- `{Sub['name']}`: {s[:100]}...")
        output.append("")

    if info["dependencies"]:
        output.append("**Dependencies (Outgoing)**:")
        for dep in info["dependencies"]:
            output.append(f"- Depends on `{dep['target']}` (Weight: {dep['weight']})")

    return "\n".join(output)
