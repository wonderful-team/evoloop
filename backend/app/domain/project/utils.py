import logging
import os

from app.constants import DEFAULT_PROJECT_ID
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


async def get_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    - project_id == DEFAULT_PROJECT_ID (0, Global Mode): Returns WORKSPACE_ROOT from SystemConfig
    - project_id > 0: Cloud API → Local DB
    """
    # 全局模式特判：返回 WORKSPACE_ROOT 作为文件读/搜索的基准目录
    # 注意：上传写入不走此函数，由 API 层直接路由至 settings.CHAT_UPLOAD_DIR
    if project_id == DEFAULT_PROJECT_ID:
        from app.infrastructure.config.service import SystemConfigService
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT", "")
        return workspace_root or ""

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
