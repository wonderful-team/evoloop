from typing import Literal, Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.domain.codebase.analysis.tools import find_definition
from app.domain.codebase.retrieval.tools import search_codebase

# ... (Delegate imports removed as they are now in actions)
# Import the new dispatched tool
from app.domain.tools.files.dispatcher import manage_file
from app.domain.tools.git import (
    git_commit,
    git_create_branch,
    git_diff,
    git_history,
    git_status,
)
from app.domain.tools.memory import (
    add_concept,
    get_user_preferences,
    save_preference,
    search_concepts,
)

# Imports for delegation
# Imports for delegation
from app.infrastructure.filesystem.tool import grep_files


@evoloop_tool
async def manage_file_read_only(
    action: Literal['list_tree', 'read'],
    path: str | None = None,
    recursive: bool = False,
    depth: int = 2,
    file_limit: int = 50,
    start_line: int | None = None,
    end_line: int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    [READ-ONLY] Use this tool to explore the filesystem. You CANNOT write or modify files.
    """
    # Force safe actions
    if action not in ['list_tree', 'read']:
         return f"Error: Action '{action}' is not allowed in Read-Only mode."

    # Validation Fix: Default path to current directory if None for list_tree
    safe_path = path if path is not None else "."

    return await manage_file.ainvoke({
        "action": action,
        "path": safe_path,
        "recursive": recursive,
        "depth": depth,
        "file_limit": file_limit,
        "start_line": start_line,
        "end_line": end_line
    }, config=config)

@evoloop_tool
async def manage_file_docs_only(
    action: Literal['list_tree', 'read', 'create', 'update_block'],
    path: str | None = None,
    content: str | None = None,
    target: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    [DOCS-ONLY] Use this tool to write documentation (.md, .txt) ONLY. 
    You CANNOT modify code files (.py, .php, etc).
    """
    # 1. Extension Check
    if action in ['create', 'update_block', 'write']:
        if not path: return "Error: Path is required for write actions."
        valid_exts = ['.md', '.txt', '.json', '.yaml', '.yml', '.csv']
        if not any(path.endswith(ext) for ext in valid_exts):
             return f"Error: Permission Denied. You may only write to {valid_exts}. For code changes, route to Coder."

    # 2. Proxy to real tool
    return await manage_file.ainvoke({
        "action": action,
        "path": path,
        "content": content,
        "target": target
    }, config=config)



@evoloop_tool
async def explore_codebase(
    action: Literal['search_symbol', 'search_text', 'semantic_code_search', 'analyze_impact'],
    query: str,
    scope_path: str | None = None, # Optional file pattern or path
    config: Annotated[RunnableConfig, InjectedToolArg] = None
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

    if action == 'search_symbol':
        return await find_definition.ainvoke({"symbol_name": query, "file_pattern": scope_path}, config=config)

    elif action == 'search_text':
        # Delegate to grep
        args = {"pattern": query, "is_regex": True}
        if scope_path: args["path"] = scope_path
        return grep_files.invoke(args, config=config)

    elif action == 'semantic_code_search':
        return await search_codebase.ainvoke({"query": query}, config=config)

    elif action == 'analyze_impact':
        return await analyze_impact.ainvoke({"symbol_name": query}, config=config)

    return f"Error: Unknown action '{action}'"


@evoloop_tool
def manage_git(
    action: Literal['status', 'diff', 'commit', 'log', 'create_branch'],
    argument: str | None = None, # message for commit, branch name, etc.
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Unified Git Operations.
    
    Args:
        action: Git command.
        argument: Contextual argument (commit message, branch name).
    """
    if action == 'status':
        return git_status.invoke({}, config=config)
    elif action == 'diff':
        return git_diff.invoke({}, config=config)
    elif action == 'commit':
        if not argument: return "Error: 'argument' (message) required for commit."
        return git_commit.invoke({"message": argument}, config=config)
    elif action == 'log':
        return git_history.invoke({}, config=config)
    elif action == 'create_branch':
        if not argument: return "Error: 'argument' (branch_name) required."
        return git_create_branch.invoke({"branch_name": argument}, config=config)

    return f"Error: Unknown action '{action}'"


@evoloop_tool
async def manage_memory(
    action: Literal['save_preference', 'retrieve_preferences', 'add_concept', 'search_concepts'],
    key: str | None = None, # concept name or pref key
    value: str | None = None, # description or pref value
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Unified Memory Management.
    """
    # Assuming user_id is handled implicitly or 'user_default'
    user_id = "user_default"

    if action == 'save_preference':
        if not key or not value: return "Error: key/value required."
        return await save_preference.ainvoke({"key": key, "value": value}, config=config)

    elif action == 'retrieve_preferences':
        return await get_user_preferences.ainvoke({"user_id": user_id}, config=config)

    elif action == 'add_concept':
        if not key or not value: return "Error: key (name) and value (description) required."
        return await add_concept.ainvoke({"name": key, "description": value}, config=config)

    elif action == 'search_concepts':
        if not key: return "Error: key (query) required."
        return await search_concepts.ainvoke({"query": key}, config=config)

    return f"Error: Unknown action '{action}'"


from app.utils.context import get_context


@evoloop_tool
async def consult_architecture(path: str = ""):
    """
    [ARCHITECT MODE] Consult the system's architectural documentation for a specific directory/module.
    Returns the module's role, sub-modules, and dependencies.
    Use this BEFORE refactoring or adding complex features to understand the ecosystem.
    
    Args:
        path: The relative path of the directory to inspect (e.g., "backend/app/core"). Defaults to root ("").
    """
    ctx = get_context()
    project_id = ctx.get("project_id")

    if not project_id:
        return "Error: No active project context."

    from app.domain.memory.service import memory_service

    info = await memory_service.get_directory_info(project_id, path)

    output = [f"# Architecture Report: {info['path'] or 'Root'}"]
    output.append(f"**Summary**: {info['summary']}\n")

    if info['sub_modules']:
        output.append("**Sub-Modules**:")
        for Sub in info['sub_modules']:
            # Truncate summary for brevity
            s = Sub['summary'] or "No summary"
            output.append(f"- `{Sub['name']}`: {s[:100]}...")
        output.append("")

    if info['dependencies']:
        output.append("**Dependencies (Outgoing)**:")
        for dep in info['dependencies']:
            output.append(f"- Depends on `{dep['target']}` (Weight: {dep['weight']})")

    return "\n".join(output)

