from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.core.tools import evoloop_tool, get_working_directory
from app.domain.codebase.retrieval.graph_service import graph_retrieval_service
from app.utils import render_template
from app.utils.process import run_command


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "查找定义", "en": "Find Definition"}
)
async def find_definition(symbol_name: str, file_pattern: str | None = None, config: RunnableConfig | None = None) -> str:
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
    results = await graph_retrieval_service.find_symbol_definition(symbol_name, project_id)
    if results:
        summaries = [f"{r['full_name']} ({r['type']}) in {r['file_path']}" for r in results]
        return render_template("domain/codebase/codebase_indexing.prompt.j2", summaries=summaries)


    # 2. Fallback to Heuristic Search (Grep)
    # Useful if file is new/modified and not yet indexed
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
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "影响分析", "en": "Analyze Impact"}
)
async def analyze_impact(symbol_name: str, config: RunnableConfig | None = None) -> str:
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

        relations_data = []
        for usage in usages:
            relations_data.append({
                "source": usage["source"],
                "direction": usage["relation"],
                "target": usage["file_path"]
            })
        
        return render_template("domain/codebase/codebase_indexing.prompt.j2", relations=relations_data)

    except Exception as e:
        return f"Error searching graph: {e}"
