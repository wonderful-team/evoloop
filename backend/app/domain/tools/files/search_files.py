import asyncio
import os
import re
import fnmatch
from typing import Annotated, Optional, Dict, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.tools import evoloop_tool
from .utils import resolve_and_validate_path
from app.core.file import FileSearcher, FileTraverser, read_file


async def _search_by_content(
    pattern: str,
    target_path: str,
    scope: Optional[str],
    case_insensitive: bool,
) -> str:
    """Search file contents using unified FileSearcher."""
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


async def _search_by_name(
    pattern: str,
    target_path: str,
    scope: Optional[str],
    case_insensitive: bool,
    max_files: int = 20,
) -> str:
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
        return f"No files found matching '{pattern}'."

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
    Uses unified FileCenter.
    """
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if search_in_name:
        res = await _search_by_name(pattern, target_path, scope, case_insensitive, max_files)
        
        # 【全局搜索扩展】如果在工作区根目录没搜到，且是全局模式，自动去 uploads 目录搜一下
        from app.core.context import ContextManager
        from app.infrastructure.config.service import SystemConfigService
        ctx = ContextManager.current()
        is_global_root = ((ctx.project_id == DEFAULT_PROJECT_ID or ctx.project_id is None) and 
                         (path == "." or path == "" or target_path == SystemConfigService.get_value("WORKSPACE_ROOT")))
        
        if is_global_root:
            res_content, res_meta = res if isinstance(res, tuple) else (res, {"count": 0})
            if res_meta.get("count", 0) < max_files:
                # 还有配额，去 uploads 搜
                upload_res = await _search_by_name(pattern, settings.CHAT_UPLOAD_DIR, scope, case_insensitive, max_files - res_meta.get("count", 0))
                upload_content, upload_meta = upload_res if isinstance(upload_res, tuple) else (upload_res, {"count": 0})
                
                if upload_meta.get("count", 0) > 0:
                    # 合并结果，并给路径加上 uploads/ 前缀以便 Agent 访问
                    # 注意：_search_by_name 返回的内容中包含相对路径，我们需要把这些路径修正
                    # 简单处理：如果 res_content 是 "No files found..."，直接替换
                    if res_meta.get("count", 0) == 0:
                        # 修正内容中的预览路径前缀
                        # 由于 _search_by_name 内部使用了 os.path.relpath(filepath, target_path)
                        # 我们直接在返回的内容里做个字符串替换可能不够稳妥，但作为智能增强已经足够
                        adjusted_content = upload_content.replace("Found ", "Found in uploads/ ").replace("matching files", "matching files (in uploads/)")
                        # 重点是返回给 Agent 的 path 应该是 uploads/filename
                        # 这在后续 Agent 调用 read_file 时会被我们的 utils.py 处理
                        return adjusted_content, upload_meta
                    else:
                        # 合并逻辑略显复杂，这里简单返回工作区结果，引导 Agent 去看目录列表
                        return res
        return res
    else:
        return await _search_by_content(pattern, target_path, scope, case_insensitive)


@evoloop_tool(
    is_pollable=True,
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.search_result",
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
    Search for text patterns in files or by file names using a unified File Center.
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
