"""
Unified Code Exploration Tools - Semantic Interface

6 semantic tools for code exploration:
- find_symbol: Find symbol definitions
- search_code: Search code patterns
- ask_codebase: Natural language queries
- analyze_impact: Dependency analysis
- check_types: Type checking
- inspect_symbol: Symbol details
"""

import logging
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.utils import render_template
from .engine import get_exploration_engine

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "查找符号", "en": "Find Symbol"}
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
        return render_template("codebase/codebase_indexing.prompt.j2", summaries=summaries)
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
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "询问代码库", "en": "Ask Codebase"}
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
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        try:
            manager = container.memory_manager
            results = await manager.long_term.search_concepts_data(question, project_id)
            
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
        finally:
            await container.shutdown()
        
    except Exception as e:
        logger.error(f"Ask codebase failed: {e}")
        return f"Error searching codebase: {e}"


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "分析影响", "en": "Analyze Impact"}
)
async def analyze_impact(
    symbol: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Analyze what would be affected by changing a symbol.
    
    Finds all usages and dependencies of a symbol to understand
    the impact of potential changes.
    
    Args:
        symbol: The symbol to analyze (e.g., "UserService.update", "process_data")
    
    Examples:
        analyze_impact(symbol="AuthMiddleware")
        analyze_impact(symbol="DatabaseConnection")
    """
    if not symbol:
        return "Error: Symbol name is required."
    
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)
    
    engine = get_exploration_engine()
    usages = await engine.analyze_impact(symbol, project_id)
    
    if not usages:
        return f"No usages found for '{symbol}'. It may be safe to modify."
    
    lines = [f"- {u.get('caller', 'unknown')} in {u.get('file_path', 'unknown')}:{u.get('line', 0)}" for u in usages[:20]]
    return f"Found {len(usages)} usages of '{symbol}':\n" + "\n".join(lines)


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "检查类型", "en": "Check Types"}
)
async def check_types(
    file_path: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Check for type errors and code issues in a file.
    
    Uses Language Server Protocol (LSP) to analyze the file
    and report errors, warnings, and type issues.
    
    Args:
        file_path: Path to the file to check
    
    Examples:
        check_types(file_path="src/services/user.py")
        check_types(file_path="components/Auth.tsx")
    """
    if not file_path:
        return "Error: File path is required."
    
    repo_path = get_working_directory(config)
    full_path = f"{repo_path}/{file_path}" if not file_path.startswith("/") else file_path
    
    engine = get_exploration_engine()
    diagnostics = await engine.check_types(full_path, repo_path)
    
    if not diagnostics:
        return f"No type issues found in {file_path}."
    
    # Check if first item is an error message
    if len(diagnostics) == 1 and "error" in diagnostics[0]:
        return f"Type check failed: {diagnostics[0]['error']}"
    
    lines = []
    for d in diagnostics:
        severity = d.get('severity', 'Error')
        line = d.get('line', 0)
        msg = d.get('message', '')
        lines.append(f"{severity} at line {line}: {msg}")
    
    return f"Type issues in {file_path}:\n" + "\n".join(lines[:20])


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "查看符号", "en": "Inspect Symbol"}
)
async def inspect_symbol(
    name: str,
    file_path: Optional[str] = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Show detailed information about a symbol (type, documentation, signature).
    
    Equivalent to IDE's "hover" or "peek definition" feature.
    Shows type information, docstrings, and usage context.
    
    Args:
        name: Symbol name to inspect
        file_path: Optional file path hint (for disambiguation)
    
    Examples:
        inspect_symbol(name="UserService")
        inspect_symbol(name="process_data", file_path="src/utils.py")
    """
    if not name:
        return "Error: Symbol name is required."
    
    # For now, combine find_symbol and search_code to provide detailed info
    repo_path = get_working_directory(config)
    engine = get_exploration_engine()
    
    # Get definition
    definition = await engine.find_symbol(name, repo_path=repo_path)
    
    # Get usages
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)
    usages = await engine.analyze_impact(name, project_id)
    
    result_parts = [f"Symbol: {name}\n"]
    
    if definition:
        result_parts.append("Definition:")
        results = definition.get("results", [])
        for r in results[:3]:
            result_parts.append(f"  - {r.get('file_path', 'unknown')}:{r.get('line', 0)}")
    
    if usages:
        result_parts.append(f"\nUsages ({len(usages)} total):")
        for u in usages[:5]:
            result_parts.append(f"  - {u.get('file_path', 'unknown')}:{u.get('line', 0)}")
    
    return "\n".join(result_parts) if len(result_parts) > 1 else f"No information found for '{name}'."
