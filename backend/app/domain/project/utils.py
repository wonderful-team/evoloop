import logging
import os

from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


async def get_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    1. Cloud API (evocloud_manager.get_project_by_id) → project.path
    2. Local DB (Repository table) → repo.local_path
    """
    # 1. Try Cloud API
    try:
        project = await evocloud_manager.get_project_by_id(project_id)
        if project and project.path and os.path.isdir(project.path):
            return project.path
    except Exception as e:
        logger.debug(f"Cloud lookup failed for {project_id}: {e}")

    # 2. Try local DB
    try:
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import session_scope
        from app.models.codebase import Repository

        async with session_scope() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repo = result.scalar_one_or_none()
            if repo and repo.local_path and os.path.isdir(repo.local_path):
                return repo.local_path
    except Exception as e:
        logger.debug(f"DB lookup failed for {project_id}: {e}")

    return ""
