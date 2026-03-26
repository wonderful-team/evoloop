import asyncio
import logging

from app.core.context.manager import ContextManager
from app.utils import render_template
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool
from app.domain.codebase.retrieval.graph_service import graph_service
from app.domain.codebase.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "搜索代码库", "en": "Search Codebase"}
)
async def search_codebase(query: str, project_id: int | None = None) -> str:
    """
    Search the codebase using a combination of Graph (symbol) search and Vector (semantic) search.

    1. Checks if 'query' matches a Class or Function name (e.g. "User").
       If found, shows relationships (Inheritance, Calls).
    2. Performs semantic search for code snippets relevant to 'query'.

    Use this for ALL code questions.

    Args:
        query: Search query (e.g. "auth middleware" or "BaseExtractor").
        project_id: Project context. Optional. Auto-detected if omitted.
                   Can be provided to temporarily override global mode.
    """
    retriever = RetrievalService()
    output_parts = []

    # Resolve project ID - allow temp project request in global mode
    pid = ContextManager.resolve_project_id(project_id, allow_global=False, request_temp=True)

    # If in global mode (pid=0), request project via HITL
    if pid == 0:
        result = await require_project_for_tool(
            tool_name="search_codebase",
            tool_category="code_search",
            prompt="Please select a project to search code:"
        )
        if isinstance(result, str):
            return result  # User cancelled
        pid = result

    # Use provided project_id if available (explicit override)
    if project_id is not None:
        pid = project_id

    # Run both searches in parallel
    graph_task = None
    if len(query.split()) < 3:
        graph_task = asyncio.create_task(retriever.get_entity_relations(query, project_id=pid))

    vector_task = asyncio.create_task(retriever.search(query, project_id=pid, limit=5))

    graph_data = None
    if graph_task:
        try:
            graph_result = await graph_task
            if graph_result and "error" not in graph_result:
                relations = graph_result.get("relations", {})
                graph_data = {
                    "symbol": graph_result.get("symbol", "Unknown"),
                    "type": graph_result.get("type", "Unknown"),
                    "file": graph_result.get("file", "Unknown"),
                    "outgoing": relations.get("outgoing", []),
                    "incoming": relations.get("incoming", [])
                }
        except Exception as e:
            logger.error(f"Graph lookup failed: {e}")

    rag_results = []
    try:
        results = await vector_task
        if results:
            rag_results = results
    except Exception as e:
        logger.error(f"RAG search failed: {e}")

    try:
        return render_template(
            "codebase/codebase_retrieval.prompt.j2",
            graph_result=graph_data,
            rag_results=rag_results
        )
    except Exception as e:
        logger.error(f"Failed to render Codebase Retrieval template: {e}")
        return "Search results processing error."


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "自然语言查询图谱", "en": "Query Graph (NL)"}
)
async def query_graph_natural_language(question: str, project_id: int) -> str:
    """
    Explore the codebase knowledge graph using natural language.
    Useful for architectural questions, finding relationships, or understanding data flow.
    Example: "Which functions depend on the User class?" or "How is the project structured?"

    Args:
        question: The natural language question to ask.
        project_id: The ID of the project to query.
    """
    return await graph_service.natural_language_query(question, project_id)
