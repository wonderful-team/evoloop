from langchain_core.tools import tool
from app.domain.codebase.indexing.service import IndexingService
import asyncio


@tool
async def index_path(path: str) -> str:
    """
    Index a specific directory or file into the knowledge base.
    Use this when you find new relevant files that need to be understood.
    """
    service = IndexingService()
    try:
        # Infer repo details
        repo_name = "current_repo"
        repo = await service.get_or_create_repo(".", repo_name)
        
        await service.index_repository(path, repo.id)
        return f"Successfully indexed {path}."
    except Exception as e:
        return f"Error indexing {path}: {str(e)}"
