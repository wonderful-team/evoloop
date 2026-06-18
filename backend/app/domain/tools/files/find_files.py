import os
import re
import fnmatch
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.tools import evoloop_tool
from .utils import resolve_and_validate_path
from app.core.file import FileTraverser, read_file


async def _search_by_name(
    pattern: str,
    target_path: str,
    scope: Optional[str],
    case_insensitive: bool,
    max_files: int = 20,
) -> tuple[str, dict]:
    """
    Search files by name and return matching paths with a short smart preview.
    Uses unified FileTraverser.
    """
    MAX_PREVIEW_LINES = 3
    q_lower = pattern.lower() if case_insensitive else pattern
    
    matched_files = []
    
    # Use unified walker
    for full_path in FileTraverser.walk(target_path):
        filename = os.path.basename(full_path)
        rel_path = os.path.relpath(full_path, target_path)
        
        # Check name pattern
        name_match = q_lower in filename.lower() if case_insensitive else pattern in filename
        
        # Check scope (glob)
        scope_match = True
        if scope:
            scope_match = fnmatch.fnmatch(rel_path, scope) or fnmatch.fnmatch(filename, scope)
            
        if name_match and scope_match:
            matched_files.append(full_path)
            if len(matched_files) >= max_files:
                break

    if not matched_files:
        return f"No files found matching '{pattern}'.", {"count": 0}

    # Build output with smart previews
    entries = []
    definition_pattern = re.compile(
        r'^\s*(class\s+|function\s+|def\s+|trait\s+|interface\s+)',
        re.IGNORECASE
    )
    
    for idx, filepath in enumerate(matched_files, 1):
        rel_path = os.path.relpath(filepath, target_path)
        
        preview_lines = []
        try:
            content = read_file(filepath).content
            all_lines = content.splitlines()
            
            # Find a definition line for a smarter preview
            start_idx = 0
            for i, line in enumerate(all_lines[:200]): # Search first 200 lines
                if definition_pattern.search(line):
                    start_idx = i
                    break
            
            for i in range(start_idx, min(start_idx + MAX_PREVIEW_LINES, len(all_lines))):
                preview_lines.append(f"     {i+1:3d}: {all_lines[i]}")
        except Exception as e:
            preview_lines.append(f"     [Could not read preview: {e}]")

        preview_block = "\n".join(preview_lines) if preview_lines else "     (empty file)"
        entries.append(f"  {idx}. {rel_path}\n     Preview:\n{preview_block}")

    header = f"Found {len(matched_files)} matching files:\n"
    if len(matched_files) >= max_files:
        header += f"(Showing first {max_files} matches; use more specific pattern to filter)\n"
    
    footer = (
        "\n\nUse read_file(path='<selected_path>') to read the full content of a file.\n"
        "If none of these look right, refine your search pattern or scope."
    )
    
    return header + "\n\n".join(entries) + footer, {"count": len(matched_files)}


async def find_files_internal(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    max_files: int = 20,
    config: RunnableConfig | None = None,
) -> tuple[str, dict]:
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e), {"count": 0}

    res_content, res_meta = await _search_by_name(pattern, target_path, scope, case_insensitive, max_files)
    
    # 【全局搜索扩展】如果在工作区根目录没搜到，且是全局模式，自动去 uploads 目录搜一下
    from app.core.context import ContextManager
    from app.infrastructure.config.service import SystemConfigService
    ctx = ContextManager.current()
    is_global_root = ((ctx.project_id == DEFAULT_PROJECT_ID or ctx.project_id is None) and 
                     (path == "." or path == "" or target_path == SystemConfigService.get_value("WORKSPACE_ROOT")))
    
    if is_global_root:
        if res_meta.get("count", 0) < max_files:
            # 还有配额，去 uploads 搜
            upload_content, upload_meta = await _search_by_name(
                pattern, settings.CHAT_UPLOAD_DIR, scope, case_insensitive, max_files - res_meta.get("count", 0)
            )
            
            if upload_meta.get("count", 0) > 0:
                if res_meta.get("count", 0) == 0:
                    adjusted_content = upload_content.replace("Found ", "Found in uploads/ ").replace("matching files", "matching files (in uploads/)")
                    return adjusted_content, upload_meta
                else:
                    return res_content, res_meta
    return res_content, res_meta


@evoloop_tool(
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.search_result",
)
async def find_files(
    pattern: str,
    path: str = ".",
    scope: Optional[str] = None,
    case_insensitive: bool = False,
    max_files: int = 20,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Find files by their names (like the `find` command).
    Returns file paths matching the given name pattern, along with short smart previews.

    Args:
        pattern: The text to search for in filenames. **REQUIRED**
        path: Directory path to search in (default: current directory).
        scope: Optional glob pattern to limit the files searched (e.g., "*.py", "src/services/*").
        case_insensitive: If True, performs a case-insensitive match on the filename.
        max_files: Maximum number of files to return (default 20).
    """
    res_content, res_meta = await find_files_internal(
        pattern=pattern,
        path=path,
        scope=scope,
        case_insensitive=case_insensitive,
        max_files=max_files,
        config=config,
    )
    return res_content, res_meta
