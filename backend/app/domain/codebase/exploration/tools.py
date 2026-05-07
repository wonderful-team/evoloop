"""
Unified Code Exploration Tools - Semantic Interface

2 semantic tools for code exploration:
- find_symbol: Find symbol definitions (Graph → LSP → Grep fallback)
- ask_codebase: Natural language queries (semantic search → code search fallback)
"""

import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.utils import render_template
from .engine import get_exploration_engine

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.search_code"
)
async def find_symbol(
    name: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Find the definition of a symbol (class, function, variable, etc.).
    
    This tool automatically uses the best available backend:
    1. Knowledge Graph (fastest, for indexed symbols)
    2. LSP (real-time, for currently open files)
    3. Grep (fallback, always available)
    
    Use this when you need to locate where a specific symbol is defined.
    
    Args:
        name: The symbol name to find (e.g., "UserService", "process_data", "MAX_RETRY")
    
    Examples:
        find_symbol(name="AuthMiddleware")
        find_symbol(name="calculate_total")
    """
    if not name:
        return "Error: Symbol name is required."
    
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)
    repo_path = get_working_directory(config)
    
    engine = get_exploration_engine()
    result = await engine.find_symbol(name, project_id, repo_path)
    
    if not result:
        return f"No definition found for symbol '{name}'."
    
    source = result.get("source", "unknown")
    results = result.get("results", [])
    
    # Format based on source
    if source == "graph":
        summaries = [f"{r.get('full_name', name)} ({r.get('type', 'unknown')}) in {r.get('file_path', 'unknown')}" for r in results]
        return render_template("domain/codebase/codebase_indexing.prompt.j2", summaries=summaries)
    elif source == "grep":
        lines = [f"{r.get('file_path')}:{r.get('line')}: {r.get('content', '')}" for r in results]
        return f"Found '{name}' via text search:\n" + "\n".join(lines[:10])
    else:
        return f"Found '{name}': {results}"


# NOTE: search_code 已合并到 search_files
# 请使用 search_files(pattern, scope, case_insensitive) 替代
# search_files 提供了相同的功能，支持 ripgrep/grep，并添加了 scope 参数


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.search_code"
)
async def ask_codebase(
    question: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Ask a natural language question about the codebase.
    
    This uses semantic search to find relevant code based on meaning,
    not just text matching. Good for questions like "how does X work?"
    
    Args:
        question: Natural language question about the code
    
    Examples:
        ask_codebase(question="How does authentication work?")
        ask_codebase(question="Where is the database connection configured?")
        ask_codebase(question="How are tasks scheduled?")
    """
    if not question:
        return "Error: Question is required."
    
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)
    
    try:
        # Use existing semantic search from memory_manager
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        results = await manager.search_concepts_data(question, project_id)
        
        if not results:
            # Fallback to code search
            engine = get_exploration_engine()
            code_results = await engine.search_code(question, None, get_working_directory(config))
            if code_results:
                lines = [f"{r.get('file_path')}:{r.get('line')}: {r.get('content', '')}" for r in code_results[:10]]
                return f"Found relevant code for '{question}':\n" + "\n".join(lines)
            return f"No relevant information found for '{question}'."
        
        # Format concept results
        lines = [f"- {r.get('name')}: {r.get('description', '')}" for r in results[:10]]
        return f"Relevant concepts for '{question}':\n" + "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Ask codebase failed: {e}")
        return f"Error searching codebase: {e}"
