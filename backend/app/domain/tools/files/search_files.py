import asyncio
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.core.tools import evoloop_tool
from app.utils.process import run_command
from .utils import resolve_and_validate_path


def _has_ripgrep() -> bool:
    """Check if ripgrep (rg) is available."""
    import shutil
    return shutil.which("rg") is not None


async def search_files_internal(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    """
    Internal function to search for text patterns in files.
    Uses ripgrep (rg) if available, fallback to grep.
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # Use ripgrep if available, fallback to grep
    if _has_ripgrep():
        cmd = ["rg", "-n", "--json"]
        if case_insensitive:
            cmd.append("-i")
        if scope:
            cmd.extend(["-g", scope])
        for exclude_dir in DEFAULT_EXCLUDED_DIRS:
            cmd.extend(["-g", f"!{exclude_dir}"])
        cmd.append(pattern)
        cmd.append(target_path)
    else:
        cmd = ["grep", "-r", "-n"]
        if case_insensitive:
            cmd.append("-i")
        if scope:
            cmd.extend(["--include", scope])
        for excluded_dir in DEFAULT_EXCLUDED_DIRS:
            cmd.append(f"--exclude-dir={excluded_dir}")
        cmd.append(pattern)
        cmd.append(target_path)

    res = await asyncio.to_thread(run_command, cmd)
    if not res.success:
        # grep returns 1 if no lines found
        if res.returncode == 1:
            return "No matches found."
        return f"Error running search: {res.stderr}"

    # Output budget check
    MAX_MATCHES = 100
    lines = res.stdout.strip().split('\n') if res.stdout else []

    if len(lines) > MAX_MATCHES:
        return f"""Error: Too many matches.

Found {len(lines)} matches, but maximum is {MAX_MATCHES} per call.

Please refine your search:
- Use a more specific pattern
- Narrow the scope with 'path' parameter
- Use file extension filter with 'scope' parameter

Example:
  search_files(pattern="class UserService", path="src/services", scope="*.py")
"""

    return res.stdout


@evoloop_tool(
    is_pollable=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.search_code",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "搜索文件", "en": "Search Files"}
)
async def search_files(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search for text patterns in files using ripgrep (rg) or grep.
    Supports regex patterns, file filtering, and case-insensitive search.

    Output Limit: Maximum 100 matches per call.
    If you hit this limit, refine your search pattern or narrow the scope.

    Useful for finding all occurrences of a function, class, variable, TODO, etc.

    Args:
        pattern: The search pattern. **REQUIRED** (supports regex)
        path: Directory or file path to search in (default: current directory).
        scope: Optional file pattern to limit search (e.g., "*.py", "src/services/*").
        case_insensitive: If True, performs case-insensitive search.

    Examples:
        search_files(pattern="def main", path="src/")
        search_files(pattern="TODO", case_insensitive=True)
        search_files(pattern="UserService", scope="*.ts")
        search_files(pattern="class.*Service", scope="backend/*.py")
    """
    return await search_files_internal(
        pattern=pattern,
        path=path,
        scope=scope,
        case_insensitive=case_insensitive,
        config=config
    )
