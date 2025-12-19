from langchain_core.tools import tool
from app.domain.codebase.retrieval.service import RetrievalService


@tool
async def search_codebase(query: str, project_id: int = 1) -> str:
    """
    Search the codebase using vector similarity. Returns code snippets.
    Use this when you want to find code usage, definitions, or examples.
    
    Args:
        query: Search query (e.g. "auth middleware").
        project_id: The ID of the project to search in. Default to 1 (current).
    """
    retriever = RetrievalService()
    try:
        results = await retriever.search(query, project_id=project_id, limit=5)
        if not results:
            return "No relevant code found."
        
        output = []
        for r in results:
            output.append(f"File: {r['file_path']}\nType: {r['chunk_type']}\nContent:\n{r['content']}\n---")
        
        return "\n".join(output)
    except Exception as e:
        return f"Error searching codebase: {str(e)}"
