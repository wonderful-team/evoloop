from app.core.tools.base import evoloop_tool


@evoloop_tool(is_pollable=False)
async def search_web(query: str) -> str:
    """
    Searches the web for the given query using DuckDuckGo.
    Returns a list of search results with titles and URLs.
    """
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for result in ddgs.text(query, max_results=5):
                results.append(
                    f"Title: {result['title']}\n"
                    f"URL: {result['href']}\n"
                    f"Description: {result['body']}\n"
                )

        if not results:
            return "No results found."

        return "\n---\n".join(results)

    except ImportError:
        return (
            "Error: duckduckgo_search package not installed. "
            "Please install it with: pip install duckduckgo-search"
        )
    except Exception as e:
        error_msg = str(e)
        # Check for rate limiting or connection issues
        if any(keyword in error_msg.lower() for keyword in ["rate", "timeout", "connection", "network"]):
            return (
                f"Error searching web: {error_msg}\n\n"
                "[REASONING_TIP] Search service may be rate limited or experiencing issues. "
                "Please USE 'browser_control' to navigate to target sites directly for higher reliability."
            )
        return f"Error searching web: {error_msg}"
