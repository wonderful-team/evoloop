import asyncio
import logging
from typing import Literal

from app.core.context.manager import ContextManager
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool
from app.domain.codebase.retrieval.service import RetrievalService
from app.utils.template import render_template

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.search_code")
async def search_codebase(
    query: str,
    operator: Literal["and", "or"],
    project_id: int | None = None,
) -> str:
    """
    Search the codebase using a combination of symbol search and Vector (semantic) search.

    1. Checks if 'query' matches a Class or Function name (e.g. "User").
       If found, shows relationships (Inheritance, Calls).
    2. Performs semantic search for code snippets relevant to 'query'.

    Use this for ALL code questions.

    Args:
        query: Search query (e.g. "auth middleware" or "BaseExtractor").
        operator: How to combine multiple terms for keyword search.
                  "and" = all terms must match (more specific),
                  "or" = any term can match (broader).
        project_id: Project context. Optional. Auto-detected if omitted.
                   Can be provided to temporarily override global mode.

    Examples:
        search_codebase(query="auth middleware", operator="or")
        search_codebase(query="payment async", operator="and")  # Must contain both
        search_codebase(query="redis cache", operator="or")     # Either is fine
    """
    retriever = RetrievalService()
    output_parts = []

    pid = ContextManager.resolve_project_id(project_id, allow_global=False, request_temp=True)

    if pid == 0:
        result = await require_project_for_tool(
            tool_name="search_codebase",
            tool_category="code_search",
            prompt="Please select a project to search code:",
        )
        if isinstance(result, str):
            return result
        pid = result

    if project_id is not None:
        pid = project_id

    symbol_task = None
    usages_task = None
    if len(query.split()) < 3:
        symbol_task = asyncio.create_task(retriever.find_symbol_definition(query, project_id=pid))
        usages_task = asyncio.create_task(retriever.find_usages(query, project_id=pid))

    vector_task = asyncio.create_task(retriever.search(query, project_id=pid, limit=5, operator=operator))

    graph_data = None
    if symbol_task:
        try:
            symbol_results = await symbol_task
            if symbol_results:
                target = symbol_results[0]
                graph_data = {
                    "symbol": target.get("full_name", "Unknown"),
                    "type": target.get("type", "Unknown"),
                    "file": target.get("file_path", "Unknown"),
                    "outgoing": target.get("outgoing", []),
                    "incoming": [],
                }
                if usages_task:
                    usages = await usages_task
                    if usages:
                        graph_data["incoming"] = [f"{u['source']} (references)" for u in usages]
        except Exception as e:
            logger.error(f"Symbol lookup failed: {e}")

    rag_results = []
    try:
        results = await vector_task
        if results:
            rag_results = results
    except Exception as e:
        logger.error(f"RAG search failed: {e}")

    count = len(rag_results)
    if graph_data:
        count += 1

    try:
        content = render_template(
            "domain/codebase/codebase_retrieval.prompt.j2",
            graph_result=graph_data,
            rag_results=rag_results,
        )
        return content, {"count": count, "pattern": query}
    except Exception as e:
        logger.error(f"Failed to render Codebase Retrieval template: {e}")
        return "Search results processing error.", {"count": 0}


@evoloop_tool(summary_template="evoloop.tool_summary.search_code")
async def query_graph_natural_language(
    question: str,
    project_id: int,
    entities: list[str],
    entity_operator: Literal["and", "or"],
) -> str:
    """
    Explore the codebase by querying relationships between entities via SQL.

    Args:
        question: The natural language context for the query.
        project_id: The ID of the project to query.
        entities: List of entity names to search for (e.g., ["pay", "notify"]).
        entity_operator: How to combine multiple entities.
                         "and" = find entities related to ALL specified entities (intersection),
                         "or" = find entities related to ANY specified entity (union).

    Examples:
        query_graph_nl(
            question="调用关系",
            project_id=DEFAULT_PROJECT_ID,
            entities=["pay", "notify"],
            entity_operator="and"
        )
        query_graph_nl(
            question="调用关系",
            project_id=DEFAULT_PROJECT_ID,
            entities=["pay", "notify"],
            entity_operator="or"
        )
    """
    retriever = RetrievalService()
    return await retriever.multi_entity_query(
        entities=entities,
        operator=entity_operator,
        question=question,
        project_id=project_id,
    )
