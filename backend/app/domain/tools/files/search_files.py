import asyncio
import os
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


async def _search_by_content(
    pattern: str,
    target_path: str,
    scope: Optional[str],
    case_insensitive: bool,
) -> str:
    """Search file contents using ripgrep or grep."""
    # Resolve symlinks so external tools (grep on macOS BSD) traverse properly
    real_target = os.path.realpath(target_path)
    if _has_ripgrep():
        cmd = ["rg", "-n", "--json"]
        if case_insensitive:
            cmd.append("-i")
        if scope:
            cmd.extend(["-g", scope])
        for exclude_dir in DEFAULT_EXCLUDED_DIRS:
            cmd.extend(["-g", f"!{exclude_dir}"])
        cmd.append(pattern)
        cmd.append(real_target)
    else:
        cmd = ["grep", "-E", "-r", "-n"]
        if case_insensitive:
            cmd.append("-i")
        if scope:
            cmd.extend(["--include", scope])
        for excluded_dir in DEFAULT_EXCLUDED_DIRS:
            cmd.append(f"--exclude-dir={excluded_dir}")
        cmd.append(pattern)
        cmd.append(real_target)

    res = await asyncio.to_thread(run_command, cmd)
    if not res.success:
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


async def _search_by_name(
    pattern: str,
    target_path: str,
    scope: Optional[str],
    case_insensitive: bool,
    max_files: int = 20,
) -> str:
    """
    Search files by name and return matching paths with a short preview.

    Uses ripgrep --files or find to list candidate files, then filters by both
    name pattern and scope using Python (ensuring AND semantics).

    Each matched file shows the first 3 lines so the LLM can quickly judge
    which file is the right one, without being overwhelmed by full content.
    """
    import fnmatch

    MAX_PREVIEW_LINES = 3

    # Step 1: List all files under target_path
    # Resolve symlinks so external tools (find/grep on macOS) traverse properly
    real_target = os.path.realpath(target_path)
    if _has_ripgrep():
        # rg --files lists all files, respecting exclusions
        exclude_args = []
        for exclude_dir in DEFAULT_EXCLUDED_DIRS:
            exclude_args.extend(["-g", f"!{exclude_dir}"])
        cmd = ["rg", "--files"]
        cmd.extend(exclude_args)
        cmd.append(real_target)
    else:
        # Fallback: use find to list all files
        cmd = ["find", real_target, "-type", "f"]

    res = await asyncio.to_thread(run_command, cmd)
    if not res.success or not res.stdout.strip():
        return "No files found matching the name pattern."

    all_files = [line.strip() for line in res.stdout.strip().split('\n') if line.strip()]

    # Step 2: Filter by name pattern AND scope (AND semantics)
    name_check = pattern.lower() if case_insensitive else pattern
    scope_check = scope.lower() if case_insensitive and scope else scope

    matched_files = []
    for filepath in all_files:
        basename = os.path.basename(filepath)
        basename_check = basename.lower() if case_insensitive else basename

        # Check name pattern (substring match)
        if name_check not in basename_check:
            continue

        # Check scope (glob pattern like "*.py")
        if scope_check and not fnmatch.fnmatch(basename_check, scope_check):
            continue

        matched_files.append(filepath)

    if not matched_files:
        return "No files found matching the name pattern."

    # Step 3: Build output with file paths and short previews
    total_files = len(matched_files)
    files_to_show = matched_files[:max_files]
    project_name = os.path.basename(target_path)

    entries = []
    for idx, filepath in enumerate(files_to_show, 1):
        # Relative path for readability
        try:
            rel = os.path.relpath(filepath, real_target)
            if rel.startswith('./'):
                rel = rel[2:]
            display_path = f"{project_name}/{rel}"
        except ValueError:
            display_path = filepath

        # Read a smart preview: try to find the first meaningful definition line
        # (class/function/def/trait/interface) and show 3 lines from there.
        preview_lines = []
        if os.path.isfile(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    all_lines = f.readlines()

                # Try to find a definition line
                import re
                definition_pattern = re.compile(
                    r'^\s*(class\s+|function\s+|def\s+|trait\s+|interface\s+)',
                    re.IGNORECASE
                )
                start_idx = 0
                for _idx, line in enumerate(all_lines):
                    if definition_pattern.search(line):
                        start_idx = _idx
                        break

                # Show up to MAX_PREVIEW_LINES from start_idx
                for i in range(start_idx, min(start_idx + MAX_PREVIEW_LINES, len(all_lines))):
                    preview_lines.append(all_lines[i].rstrip('\n'))
            except Exception as e:
                preview_lines.append(f"[Unable to preview: {e}]")
        else:
            preview_lines.append("[Not a readable file]")

        numbered = [f"     {i:3d}: {ln}" for i, ln in enumerate(preview_lines, 1)]
        preview_block = "\n".join(numbered) if numbered else "     (empty file)"

        entries.append(
            f"  {idx}. {display_path}\n"
            f"     Preview:\n"
            f"{preview_block}"
        )

    header = f"Found {total_files} file(s) matching name pattern '{pattern}'"
    if scope:
        header += f" with scope '{scope}'"
    header += ":\n"
    if total_files > max_files:
        header += f"(Showing first {max_files} files; {total_files - max_files} more not displayed)\n"
    header += "\n"

    footer = (
        "\n\nUse read_file(path='<selected_path>') to read the full content of a file.\n"
        "If none of these look right, refine your search pattern or scope."
    )

    return header + "\n\n".join(entries) + footer


async def search_files_internal(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    search_in_name: bool = True,
    max_files: int = 20,
    config: RunnableConfig | None = None,
) -> str:
    """
    Internal function to search for text patterns in files or by file names.
    Uses ripgrep (rg) if available, fallback to grep/find.
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if search_in_name:
        return await _search_by_name(pattern, target_path, scope, case_insensitive, max_files)
    else:
        return await _search_by_content(pattern, target_path, scope, case_insensitive)


@evoloop_tool(
    is_pollable=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.search_code",
    result_summary_template="database_logger.tool_summary.file_op_result"
)
async def search_files(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    search_in_name: bool = True,
    max_files: int = 20,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search for text patterns in files or by file names using ripgrep (rg) or grep/find.
    Supports regex patterns, file filtering, case-insensitive search, and name-based search.

    Output Limit (content search): Maximum 100 matches per call.
    Output Limit (name search): Maximum `max_files` files shown (default 20), 3 preview lines per file.
    If you hit these limits, refine your search pattern or narrow the scope.

    Useful for finding all occurrences of a function, class, variable, TODO, etc.
    When search_in_name=True, returns file paths with a 3-line preview of each match.

    Args:
        pattern: The search pattern. **REQUIRED** (supports regex for content, glob-like for name)
        path: Directory or file path to search in (default: current directory).
        scope: Optional file pattern to limit search (e.g., "*.py", "src/services/*").
        case_insensitive: If True, performs case-insensitive search.
        search_in_name: If True (default), searches for files whose names match the pattern
                        and returns file paths with a short preview.
                        Set to False only when you need to search inside file contents.
        max_files: Maximum number of files to display when search_in_name=True (default 20).

    Examples:
        # Search file contents
        search_files(pattern="def main", path="src/", search_in_name=False)
        search_files(pattern="TODO", case_insensitive=True, search_in_name=False)
        search_files(pattern="UserService", scope="*.ts", search_in_name=False)

        # Search by file name (with preview)
        search_files(pattern="user", path="src/")
        search_files(pattern="config", scope="*.py")
        search_files(pattern="test_", case_insensitive=True)
    """
    return await search_files_internal(
        pattern=pattern,
        path=path,
        scope=scope,
        case_insensitive=case_insensitive,
        search_in_name=search_in_name,
        max_files=max_files,
        config=config,
    )
