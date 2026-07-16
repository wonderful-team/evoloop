import os
import logging
from sqlalchemy import select
from app.models.codebase import Repository
from app.infrastructure.database import session_scope
from app.core.file import is_ignored_path

logger = logging.getLogger(__name__)

async def validate_project_path(candidate_path: str, workspace_root: str) -> None:
    """
    Validate if the candidate path is a valid project directory.
    Raises ValueError with a user-friendly error message if invalid.
    
    Checks:
    - Normalizes and resolves symlinks using realpath
    - Must reside strictly inside workspace_root (cannot be workspace_root itself)
    - Must not contain system/hidden parts (starting with '.', '~', '_')
    - Must not be in system path blacklists (is_ignored_path)
    - Must satisfy 'bi-directional exclusion' (no overlapping with existing synced/pending projects)
    """
    if not candidate_path:
        raise ValueError("Project path cannot be empty")
        
    candidate_realpath = os.path.realpath(candidate_path)
    root_realpath = os.path.realpath(workspace_root)
    
    # Must reside strictly within workspace_root
    # We check if root_realpath is a prefix of candidate_realpath
    # and candidate_realpath is not equal to root_realpath
    if candidate_realpath == root_realpath:
        raise ValueError("Cannot register the workspace root itself as a project")
        
    # Check prefix
    try:
        common = os.path.commonpath([root_realpath, candidate_realpath])
        if common != root_realpath:
            raise ValueError(f"Project path must reside within the workspace root: {workspace_root}")
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path comparison: {str(e)}")
        
    # Check hidden or system components
    relative_part = os.path.relpath(candidate_realpath, root_realpath)
    for part in relative_part.replace("\\", "/").split("/"):
        if not part:
            continue
        if part.startswith((".", "~", "_")):
            raise ValueError(f"Project path cannot contain system or hidden folder names (starting with '.', '~', or '_'): '{part}'")
            
    # Check path-based exclude lists (node_modules, venv, .git, etc.)
    if is_ignored_path(candidate_realpath):
        raise ValueError("Project path matches excluded directory names (e.g., venv, node_modules, etc.)")
        
    # Check overlapping with other registered active projects in DB
    async with session_scope() as session:
        stmt = select(Repository).where(Repository.sync_status.in_(["SYNCED", "PENDING_CREATION"]))
        result = await session.execute(stmt)
        active_repos = result.scalars().all()
        
        for repo in active_repos:
            if not repo.local_path:
                continue
            existing_realpath = os.path.realpath(repo.local_path)
            
            if candidate_realpath == existing_realpath:
                raise ValueError(f"A project is already registered at this path: '{repo.name}'")
                
            # Candidate is subdirectory of existing project
            if candidate_realpath.startswith(existing_realpath + os.sep):
                raise ValueError(
                    f"Path cannot be inside another project: '{repo.name}' ({repo.local_path})"
                )
                
            # Existing project is subdirectory of candidate (candidate contains existing project)
            if existing_realpath.startswith(candidate_realpath + os.sep):
                raise ValueError(
                    f"Path cannot contain another project: '{repo.name}' ({repo.local_path})"
                )
                
    logger.info(f"[PathValidator] Path '{candidate_path}' successfully validated (resolved: '{candidate_realpath}')")
