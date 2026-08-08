import json
import logging
import os
from pathlib import Path

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.file import FileStatus, read_file, write_file_with_verification
from app.core.project.local_index import local_project_index
from app.infrastructure.database import session_scope
from app.models import Repository

logger = logging.getLogger(__name__)


# =============================================================================
# 项目级存储路径解析器
# =============================================================================


def get_workspace_root() -> str:
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


def get_project_json_path(project_path: str) -> str:
    """Return the path to {project_path}/.evoloop/project.json."""
    return os.path.join(project_path, ".evoloop", "project.json")


def read_project_json(project_path: str) -> dict:
    """Read {project_path}/.evoloop/project.json if it exists."""
    meta_file = get_project_json_path(project_path)
    result = read_file(meta_file)
    if result.status == FileStatus.SUCCESS:
        try:
            return json.loads(result.content) or {}
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"[ProjectUtils] Failed to parse {meta_file}: {e}")
    return {}


def write_project_json(project_path: str, data: dict) -> None:
    """Write data to {project_path}/.evoloop/project.json, merging with existing content.

    Existing keys are preserved unless explicitly overwritten by `data`.
    This keeps local project.json as the truth source while allowing
    callers to update specific fields (e.g. project_id, description).
    """
    meta_file = get_project_json_path(project_path)
    read_result = read_file(meta_file)
    meta = read_project_json(project_path)
    meta.update(data)

    expected_hash = read_result.metadata.content_hash if read_result.success else None
    write_result = write_file_with_verification(
        json.dumps(meta, indent=2, ensure_ascii=False),
        meta_file,
        expected_hash=expected_hash,
    )
    if not write_result.success:
        logger.warning(f"[ProjectUtils] Failed to write {meta_file}: {write_result.message}")


async def get_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    - project_id == DEFAULT_PROJECT_ID (0, Global Mode): Returns WORKSPACE_ROOT
    - project_id > 0:
        1. Local .evoloop/project.json scan (authoritative)
        2. Repository.relative_path / local_path (fallback, read-only)
    """
    # 全局模式特判：返回 WORKSPACE_ROOT 作为文件读/搜索的基准目录
    # 注意：上传写入不走此函数，由 API 层直接路由至 settings.CHAT_UPLOAD_DIR
    if project_id == DEFAULT_PROJECT_ID:
        return get_workspace_root()

    workspace_root = get_workspace_root()

    # 1. Local project.json scan (authoritative)
    local_entry = local_project_index.get_entry(project_id, workspace_root)
    if local_entry and os.path.isdir(local_entry.path):
        return local_entry.path

    # 2. Fallback: Repository.relative_path / local_path (read-only)
    # This is a transitional fallback for projects that haven't written their
    # project_id into .evoloop/project.json yet. We intentionally do NOT mutate
    # project.json here to keep local-first authority intact.
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
                        return candidate

                if repo.local_path and os.path.isdir(repo.local_path):
                    return repo.local_path
    except Exception as e:
        logger.debug(f"DB lookup failed for {project_id}: {e}")

    return ""


async def resolve_project_to_repo(project_id: int) -> Repository | None:
    """
    Resolve a project_id to the single active Repository on this device.

    Resolution order:
    1. Local .evoloop/project.json (authoritative for path, may contain repo_id)
    2. Database lookup for active Repository with matching project_id

    Returns None if no active repository can be resolved. Logs a warning if
    multiple active repositories are found (the DB partial unique index should
    prevent this, but we defensively handle the case).
    """
    if project_id == DEFAULT_PROJECT_ID:
        return None

    workspace_root = get_workspace_root()
    local_entry = local_project_index.get_entry(project_id, workspace_root)

    try:
        async with session_scope() as session:
            # If local project.json contains a repo_id, trust it first.
            if local_entry and local_entry.repo_id is not None:
                repo = await session.get(Repository, local_entry.repo_id)
                if repo and repo.sync_status not in ("IGNORED", "DISCONNECTED"):
                    return repo

            # Otherwise, query by project_id among active repos.
            stmt = (
                select(Repository)
                .where(Repository.project_id == project_id)
                .where(Repository.sync_status.notin_(["IGNORED", "DISCONNECTED"]))
            )
            result = await session.execute(stmt)
            repos = result.scalars().all()

            if not repos:
                return None

            if len(repos) > 1:
                logger.warning(
                    f"[ProjectUtils] Multiple active repositories found for project_id "
                    f"{project_id}; using repo_id={repos[0].id}. This should not happen "
                    f"after the active-project unique index is enforced."
                )

            # Prefer a repo whose path matches the local entry if available.
            if local_entry:
                for repo in repos:
                    repo_path = repo.local_path or (
                        os.path.join(workspace_root, repo.relative_path)
                        if repo.relative_path and workspace_root
                        else None
                    )
                    if repo_path and os.path.abspath(repo_path) == os.path.abspath(
                        local_entry.path
                    ):
                        return repo

            return repos[0]
    except Exception as e:
        logger.warning(f"[ProjectUtils] Failed to resolve project_id {project_id} to repo: {e}")
        return None
