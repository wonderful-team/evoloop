from typing import Optional, Literal
from langchain_core.runnables import RunnableConfig
from app.core.tools import evoloop_tool

# Imports for delegation
# Imports for delegation
from app.infrastructure.filesystem.tool import grep_files
from app.domain.tools.document_reader import read_document
from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.codebase.analysis.tools import find_definition
from app.domain.tools.git import git_status, git_diff, git_commit, git_history, git_create_branch
from app.domain.tools.memory import save_preference, get_user_preferences, search_concepts, add_concept

# ... (Delegate imports removed as they are now in actions)

# Import the new dispatched tool
from app.domain.tools.files.dispatcher import manage_file



@evoloop_tool
async def explore_codebase(
    action: Literal['search_symbol', 'search_text', 'semantic_code_search', 'analyze_impact'],
    query: str,
    scope_path: Optional[str] = None, # Optional file pattern or path
    config: Optional[RunnableConfig] = None
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
    from app.domain.codebase.analysis.tools import find_definition, analyze_impact
    
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
    argument: Optional[str] = None, # message for commit, branch name, etc.
    config: Optional[RunnableConfig] = None
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
    key: Optional[str] = None, # concept name or pref key
    value: Optional[str] = None, # description or pref value
    config: Optional[RunnableConfig] = None
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

