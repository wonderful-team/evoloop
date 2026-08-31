import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import FileSearcher
from app.core.file.constants import MAX_MATCHES
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

from .utils import resolve_and_validate_path


async def grep_search_internal(
    pattern: str,
    path: str = ".",
    scope: str | None = None,
    case_insensitive: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    """Search file contents using unified FileSearcher."""
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    results = await FileSearcher.search_content(
        pattern=pattern,
        root_path=target_path,
        scope=scope,
        case_insensitive=case_insensitive,
        limit=MAX_MATCHES + 1,
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
    name="grep",
    affected_path_keys=["path"],
    summary_template="evoloop.tool_summary.search_result",
)
async def grep_search(
    pattern: str,
    path: str = ".",
    scope: str | None = None,
    case_insensitive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    在指定目录内搜索文件内容中的文本模式。
    使用正则做模式匹配（基于 ripgrep）。

    Args:
        pattern: 要在文件中搜索的正则或文本模式。**必填**
        path: 要搜索的目录或文件路径（默认当前目录）。
        scope: 可选 glob 模式，限制被搜索的文件（如 "*.py"、"src/services/*"）。
        case_insensitive: 为 True 时做不区分大小写的搜索。
    """
    return await grep_search_internal(
        pattern=pattern,
        path=path,
        scope=scope,
        case_insensitive=case_insensitive,
        config=config,
    )
