import json
import logging
import os
from pathlib import Path

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.evocloud import evocloud_manager
from app.core.project.local_index import local_project_index
from app.infrastructure.database.sql.database import session_scope
from app.models import Repository

logger = logging.getLogger(__name__)


# =============================================================================
# 项目级存储路径解析器
# =============================================================================


def _get_workspace_root() -> str:
    """Return WORKSPACE_ROOT from SystemConfigService, or empty string."""
    from app.infrastructure.config.service import SystemConfigService
    return SystemConfigService.get_value("WORKSPACE_ROOT", "") or ""


def get_evoloop_dir(project_path: str) -> Path:
    """
    返回 {project}/.evoloop/ 目录，不存在则创建。

    Args:
        project_path: 项目本地路径（如 /Users/xujin/Projects/evoloop）

    Returns:
        Path 对象指向 {project}/.evoloop/
    """
    p = Path(project_path) / ".evoloop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_graph_path(project_path: str) -> Path:
    """返回项目的 code_graph.json 路径"""
    return get_evoloop_dir(project_path) / "code_graph.json"


def get_vectors_path(project_path: str) -> Path:
    """返回项目的 LanceDB 向量存储目录"""
    return get_evoloop_dir(project_path) / "vectors"


def get_memory_path(project_path: str) -> Path:
    """返回项目的 memory 存储目录"""
    return get_evoloop_dir(project_path) / "memory"


def backfill_project_json(path: str, project_id: int) -> None:
    """Write or update project_id in {path}/.evoloop/project.json."""
    meta_file = os.path.join(path, ".evoloop", "project.json")
    meta: dict = {}
    if os.path.exists(meta_file):
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            logger.warning(f"[ProjectUtils] Failed to read {meta_file}: {e}")

    if meta.get("project_id") == project_id:
        return

    meta["project_id"] = project_id
    try:
        os.makedirs(os.path.dirname(meta_file), exist_ok=True)
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        logger.info(f"[ProjectUtils] Backfilled project_id {project_id} into {meta_file}")
    except Exception as e:
        logger.warning(f"[ProjectUtils] Failed to write {meta_file}: {e}")


async def get_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    - project_id == DEFAULT_PROJECT_ID (0, Global Mode): Returns WORKSPACE_ROOT
    - project_id > 0:
        1. Local .evoloop/project.json scan (authoritative)
        2. Repository.relative_path / local_path (fallback + backfill)
        3. Cloud API path (last resort + backfill)
    """
    # 全局模式特判：返回 WORKSPACE_ROOT 作为文件读/搜索的基准目录
    # 注意：上传写入不走此函数，由 API 层直接路由至 settings.CHAT_UPLOAD_DIR
    if project_id == DEFAULT_PROJECT_ID:
        return _get_workspace_root()

    workspace_root = _get_workspace_root()

    # 1. Local project.json scan (authoritative)
    local_path = local_project_index.get_path(project_id, workspace_root)
    if local_path and os.path.isdir(local_path):
        return local_path

    # 2. Fallback: Repository.relative_path / local_path
    try:
        async with session_scope() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repo = result.scalar_one_or_none()
            if repo:
                # Prefer relative_path (stable against renames/moves of WORKSPACE_ROOT)
                if repo.relative_path and workspace_root:
                    candidate = os.path.join(workspace_root, repo.relative_path)
                    if os.path.isdir(candidate):
                        backfill_project_json(candidate, project_id)
                        return candidate

                if repo.local_path and os.path.isdir(repo.local_path):
                    backfill_project_json(repo.local_path, project_id)
                    return repo.local_path
    except Exception as e:
        logger.debug(f"DB lookup failed for {project_id}: {e}")

    # 3. Last resort: Cloud API path
    try:
        project = await evocloud_manager.get_project_by_id(project_id)
        cloud_path = project.get("path") if project else None
        if cloud_path and os.path.isdir(cloud_path):
            backfill_project_json(cloud_path, project_id)
            return cloud_path
    except Exception as e:
        logger.debug(f"Cloud lookup failed for {project_id}: {e}")

    return ""
