from app.core.tools.base import evoloop_tool


@evoloop_tool
async def search_web(query: str) -> str:
    """
    Searches the web for the given query.
    Returns a list of search results with titles and URLs.
    """
    # Placeholder for actual search implementation (Google/DDG)
    # Since we don't have a verified search key in env, we'll try a basic request or mock it.
    # Ideally should use GoogleSerperAPIWrapper or similar if configured.

    # Check for simple fallback
    try:
        from googlesearch import search

        results = []
        # advanced=True yields Result objects
        for result in search(query, num_results=5, advanced=True):
            results.append(f"Title: {result.title}\nURL: {result.url}\nDescription: {result.description}\n")

        if not results:
            return "No results found."

        return "\n---\n".join(results)
    except ImportError:
        return "Error: googlesearch-python not installed. Please install it or configure a search provider."
    except Exception as e:
        return f"Error searching web: {e}"
