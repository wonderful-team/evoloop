"""Search results formatting utilities for agent-facing display.

Methods in this module turn web and chat search results into prompt-ready
strings. It is intentionally cross-domain because the same prompt template is
used by both the research tool (web) and the memory tool (chat history).
"""

from app.utils.template import render_template


def format_web_search_results(query: str, results: list) -> tuple[str, dict]:
    """Format web search results.

    Args:
        query: The original search query.
        results: List of result items.

    Returns:
        A tuple of (rendered string, metadata dict with ``count``).
    """
    return render_template(
        "common/events/search_results.prompt.j2",
        query=query,
        results=results,
        result_type="web",
    ), {"count": len(results)}


def format_chat_search_results(query: str, results: list) -> tuple[str, dict]:
    """Format chat history search results.

    Args:
        query: The original search query.
        results: Iterable of message objects with ``type`` and ``content`` attributes.

    Returns:
        A tuple of (rendered string, metadata dict with ``count``).
    """
    formatted_results = []
    for msg in results:
        role = "User" if msg.type == "human" else "Assistant"
        content = msg.content
        preview = content[:200] + "..." if len(content) > 200 else content
        formatted_results.append({"role": role, "content": preview})

    return render_template(
        "common/events/search_results.prompt.j2",
        query=query,
        results=formatted_results,
        result_type="chat",
    ), {"count": len(formatted_results)}
