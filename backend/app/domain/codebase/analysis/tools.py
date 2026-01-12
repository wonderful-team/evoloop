
from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool, get_working_directory
from app.domain.codebase.retrieval.graph_service import graph_retrieval_service


@evoloop_tool
async def find_definition(symbol_name: str, file_pattern: str | None = None, config: RunnableConfig = None) -> str:
    """
    Find the definition (class/function) of a symbol in the codebase using Knowledge Graph.
    Falls back to Grep if not found in Graph.
    
    Args:
        symbol_name: The exact name of the class or function.
        file_pattern: Optional glob pattern to limit search.
    """
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)

    # 1. Try Graph Search First (Precision)
    try:
        results = await graph_retrieval_service.find_symbol_definition(symbol_name, project_id)
        if results:
            lines = [f"Found {len(results)} definitions in Knowledge Graph:"]
            for r in results:
                lines.append(f"- {r['full_name']} ({r['type']}) in {r['file_path']}")
            return "\n".join(lines)
    except Exception:
        # Log but continue to fallback
        pass

    # 2. Fallback to Heuristic Search (Grep)
    # Useful if file is new/modified and not yet indexed
    from app.utils.process import run_command
    root = get_working_directory(config)
    cmd = ["grep", "-rnE", f"(class|def)\\s+{symbol_name}\\b", root]

    if file_pattern:
        cmd.extend(["--include", file_pattern])

    cmd.extend(["--exclude-dir", ".git", "--exclude-dir", "__pycache__", "--exclude-dir", "node_modules"])

    try:
        res = run_command(cmd)
        if res.success and res.stdout:
            lines = res.stdout.strip().splitlines()
            preview = "\n".join(lines[:10])
            return f"(Graph Miss) Found potential definitions via Grep:\n{preview}"
    except:
        pass

    return f"No definition found for symbol '{symbol_name}'."


@evoloop_tool
async def analyze_impact(symbol_name: str, config: RunnableConfig = None) -> str:
    """
    Analyze the impact of changing a symbol (Dependants/Usages).
    Uses Graph Database to find who calls/uses this symbol.
    
    Args:
        symbol_name: The symbol to analyze.
    """
    ctx = config.get("configurable", {}) if config else {}
    project_id = ctx.get("project_id", 1)

    try:
        # 1. Find Usages (Incoming edges)
        usages = await graph_retrieval_service.find_usages(symbol_name, project_id)

        if not usages:
            return f"No usages found for symbol '{symbol_name}' in the Knowledge Graph."

        lines = [f"Impact Analysis for '{symbol_name}':"]
        lines.append(f"Found {len(usages)} dependants:")

        # Group by file
        by_file = {}
        for use in usages:
            fp = use.get('file_path', 'unknown')
            if fp not in by_file: by_file[fp] = []
            by_file[fp].append(f"{use.get('source')} ({use.get('relation')})")

        for fp, items in by_file.items():
            lines.append(f"\nIn File: {fp}")
            for item in items:
                lines.append(f"  - {item}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error searching graph: {e}"
