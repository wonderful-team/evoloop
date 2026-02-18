import os

from langchain_core.tools import tool

from app.domain.codebase.indexing.service import IndexingService
from app.core.context.manager import ContextManager


@tool
async def index_path(path: str) -> str:
    """
    Index a specific directory or file into the knowledge base.
    Use this when you find new relevant files that need to be understood.
    """
    service = IndexingService()
    try:
        ctx = ContextManager.current()
        root = ctx.working_directory or os.getcwd()

        # Ensure path is absolute relative to project root
        target_path = os.path.abspath(os.path.join(root, path))

        # Get/Create Repo for the PROJECT ROOT, not the target subdir
        # This ensures all chunks belong to the same project info
        repo_name = os.path.basename(root)
        repo = await service.get_or_create_repo(root, repo_name)

        await service.index_repository(target_path, repo.id)
        return f"Successfully indexed {target_path} into repo '{repo_name}'."
    except Exception as e:
        return f"Error indexing {path}: {str(e)}"
