import os
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from .utils import resolve_and_validate_path
from app.core.file import FileSearcher


async def grep_search_internal(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    """Search file contents using unified FileSearcher."""
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    MAX_MATCHES = 100
    
    results = await FileSearcher.search_content(
        pattern=pattern,
        root_path=target_path,
        scope=scope,
        case_insensitive=case_insensitive,
        limit=MAX_MATCHES + 1
    )
    
    total_matches = len(results)
    
    # Format for Agent view
    formatted_results = []
    for r in results[:MAX_MATCHES]:
        rel_path = os.path.relpath(r["file"], target_path)
        formatted_results.append(f"{rel_path}:{r['line']}:{r['content']}")
        
    output = "\n".join(formatted_results) if formatted_results else "No matches found."

    if total_matches > MAX_MATCHES:
        output += f"\n\n... (Showing first {MAX_MATCHES} matches; more matches not displayed)\n"
        output += "\nTip: The search results are truncated because there are too many matches."
        output += "\nPlease refine your search to see more specific results."

    return output, {"count": total_matches}


@evoloop_tool(
    is_pollable=True,
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.search_result",
)
async def grep_search(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search for text patterns inside file contents in the specified directory.
    Uses regex for pattern matching (powered by ripgrep).

    Args:
        pattern: The regex or text pattern to search for inside files. **REQUIRED**
        path: Directory or file path to search in (default: current directory).
        scope: Optional glob pattern to limit the files searched (e.g., "*.py", "src/services/*").
        case_insensitive: If True, performs a case-insensitive search.
    """
    return await grep_search_internal(
        pattern=pattern,
        path=path,
        scope=scope,
        case_insensitive=case_insensitive,
        config=config,
    )
