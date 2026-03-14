from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.core.tools import evoloop_tool, get_working_directory
from app.utils.process import run_command


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code"
)
async def find_definition(symbol_name: str, file_pattern: str | None = None, config: RunnableConfig | None = None) -> str:
    """
    Find the definition (class/function) of a symbol in the codebase using Grep.

    Note: Full Knowledge Graph search is available via Cloud API.
    Client mode uses Grep for local code search.

    Args:
        symbol_name: The exact name of the class or function.
        file_pattern: Optional glob pattern to limit search.
    """
    # Use Grep for local code search
    root = get_working_directory(config)
    cmd = ["grep", "-rnE", f"(class|def)\\s+{symbol_name}\\b", root]

    if file_pattern:
        cmd.extend(["--include", file_pattern])

    cmd.extend([f"--exclude-dir={d}" for d in DEFAULT_EXCLUDED_DIRS])

    try:
        res = run_command(cmd)
        if res.success and res.stdout:
            lines = res.stdout.strip().splitlines()
            preview = "\n".join(lines[:10])
            return f"(Graph Miss) Found potential definitions via Grep:\n{preview}"
    except Exception:
        pass

    return f"No definition found for symbol '{symbol_name}'."


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code"
)
async def analyze_impact(symbol_name: str, config: RunnableConfig | None = None) -> str:
    """
    Analyze the impact of changing a symbol (Dependants/Usages).
    Uses Grep to find who calls/uses this symbol.

    Note: Full Knowledge Graph impact analysis is available via Cloud API.
    Client mode uses Grep for local code search.

    Args:
        symbol_name: The symbol to analyze.
    """
    root = get_working_directory(config)

    # Use Grep to find usages
    cmd = ["grep", "-rnE", f"\\b{symbol_name}\\b", root]
    cmd.extend([f"--exclude-dir={d}" for d in DEFAULT_EXCLUDED_DIRS])

    try:
        res = run_command(cmd)
        if not res.success or not res.stdout:
            return f"No usages found for symbol '{symbol_name}'."

        lines = res.stdout.strip().splitlines()

        # Group by file
        by_file = {}
        for line in lines[:50]:  # Limit to first 50 matches
            parts = line.split(":", 1)
            if len(parts) >= 2:
                fp = parts[0]
                content = parts[1]
                if fp not in by_file:
                    by_file[fp] = []
                by_file[fp].append(content.strip()[:80])  # Truncate long lines

        result_lines = [f"Impact Analysis for '{symbol_name}':"]
        result_lines.append(f"Found {len(lines)} potential usages (showing first 50):\n")

        for fp, items in by_file.items():
            result_lines.append(f"In File: {fp}")
            for item in items[:5]:  # Show max 5 per file
                result_lines.append(f"  - {item}")
            if len(items) > 5:
                result_lines.append(f"  ... and {len(items) - 5} more")
            result_lines.append("")

        return "\n".join(result_lines)

    except Exception as e:
        return f"Error searching code: {e}"
