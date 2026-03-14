import asyncio

from app.core.context.manager import ContextManager
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool
from app.domain.codebase.retrieval.graph_explorer import graph_explorer
from app.domain.codebase.retrieval.service import RetrievalService


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code"
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

    # 1. Handle Graph / Structure Search
    if graph_task:
        try:
            graph_result = await graph_task
            if graph_result and "error" not in graph_result:
                relations = graph_result.get("relations", {})
                outgoing = relations.get("outgoing", [])
                incoming = relations.get("incoming", [])

                graph_text = [
                    f"### 🧩 Code Structure: {graph_result['symbol']} ({graph_result['type']})"
                ]
                graph_text.append(f"File: {graph_result['file']}")
                if outgoing:
                    graph_text.append("**Outgoing Relations:**")
                    for r in outgoing:
                        graph_text.append(f"- {r}")
                if incoming:
                    graph_text.append("**Incoming Relations (Usage):**")
                    for r in incoming:
                        graph_text.append(f"- {r}")

                output_parts.append("\n".join(graph_text))
        except Exception as e:
            output_parts.append(f"(Graph lookup failed: {e})")

    # 2. Handle Semantic Search (RAG)
    try:
        results = await vector_task
        if results:
            rag_text = ["### 📄 Semantic Matches:"]
            for r in results:
                rag_text.append(f"**File**: {r['file_path']} ({r['chunk_type']})\n```\n{r['content']}\n```")
            output_parts.append("\n".join(rag_text))
        elif not output_parts:  # If graph also empty
            return "No relevant code or symbols found."

    except Exception as e:
        return f"Error searching codebase: {str(e)}"

    return "\n\n---\n\n".join(output_parts)


@evoloop_tool(
    summary_template="database_logger.tool_summary.search_code"
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
    return await graph_explorer.query(question, project_id)
