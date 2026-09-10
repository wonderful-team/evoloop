import json
import logging
import os
from pathlib import Path

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.file import FileStatus, read_file, write_file_with_verification
from app.core.project.local_index import local_project_index
from app.domain.codebase.constants import REPO_SYNC_INACTIVE_STATUSES
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


def resolve_member_workspace_root(member_id: int | None) -> str:
    """多租户用户工作根 — 唯一出处，所有按用户隔离的路径必须经由本函数。

    - MULTI_TENANT_MODE=True: ``<WORKSPACE_ROOT>/<member_id>``（不存在则创建）；
      member_id 缺失/无效返回空串（调用方按“未知用户”拒绝，绝不静默落到全局根）。
    - 单用户模式: 原 WORKSPACE_ROOT（向后兼容），member_id 不参与。

    目录命名用 member_id（稳定），不用 username（可改名导致路径漂移）。
    """
    from app.core.config import settings

    root = get_workspace_root()
    if not root:
        return ""
    if not settings.MULTI_TENANT_MODE:
        return root
    try:
        mid = int(member_id) if member_id is not None else 0
    except (TypeError, ValueError):
        return ""
    if mid <= 0:
        return ""
    member_root = os.path.join(root, str(mid))
    try:
        os.makedirs(member_root, exist_ok=True)
    except OSError as e:
        logger.warning(
            f"[ProjectUtils] Failed to create member workspace {member_root}: {e}",
            exc_info=True,
        )
        return ""
    return member_root


def current_member_id() -> int:
    """从当前执行上下文（EvoContext）解析归属会员，未知返回 0。

    供路径解析 helper 的"环境身份"兜底：engine/tools/hooks 在 EvoContext
    作用域内运行（模块 2 已保证 ctx.member_id 写入），无需改各调用点签名。
    """
    try:
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        mid = getattr(ctx, "member_id", None) or 0
        return int(mid) if mid else 0
    except Exception:
        return 0


def member_workspace_root_or_fail(member_id: int | None = None) -> str:
    """解析当前（或指定）member 的工作根；多租户下无身份返回空串（fail-closed）。"""
    return resolve_member_workspace_root(member_id if member_id else current_member_id())


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
            logger.warning(
                f"[ProjectUtils] Failed to parse {meta_file}: {e}", exc_info=True
            )
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
        logger.warning(
            f"[ProjectUtils] Failed to write {meta_file}: {write_result.message}"
        )


async def get_project_path(project_id: int, member_id: int | None = None) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    - project_id == DEFAULT_PROJECT_ID (0, Global Mode): Returns the member's
      workspace root (multi-tenant: workspace/<member>; single-user: root)
    - project_id > 0:
        1. Local .evoloop/project.json scan (authoritative, member-scoped root)
        2. Repository.relative_path / local_path (fallback, read-only,
           multi-tenant 下仅当路径落在该 member 根内才放行)

    多租户身份：优先显式 member_id，否则从执行上下文（EvoContext.member_id）
    兜底；仍未知 → 返回 ""（fail-closed：agent 拿不到本地路径即无从操作）。
    """
    from app.core.config import settings as _settings

    member = member_id if member_id else current_member_id()

    # 全局模式特判：返回（member 级）工作区根作为文件读/搜索的基准目录
    # 注意：上传写入不走此函数，由 API 层直接路由至 settings.CHAT_UPLOAD_DIR
    if project_id == DEFAULT_PROJECT_ID:
        if _settings.MULTI_TENANT_MODE and not member:
            return ""
        return resolve_member_workspace_root(member)

    member_root = (
        resolve_member_workspace_root(member) if _settings.MULTI_TENANT_MODE else ""
    )
    if _settings.MULTI_TENANT_MODE and not member_root:
        return ""

    # 多租户：扫描/解析范围锁定在 member 根内；单用户：沿用全局根
    scan_root = member_root or get_workspace_root()

    # 1. Local project.json scan (authoritative)
    local_entry = local_project_index.get_entry(project_id, scan_root)
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
                if repo.relative_path and scan_root:
                    candidate = os.path.join(scan_root, repo.relative_path)
                    if os.path.isdir(candidate):
                        return candidate

                if repo.local_path and os.path.isdir(repo.local_path):
                    # 多租户下 local_path 必须落在该 member 根内，防止 DB 脏数据
                    # 越界到其他用户目录/宿主任意路径。
                    if not _settings.MULTI_TENANT_MODE:
                        return repo.local_path
                    if member_root and os.path.realpath(repo.local_path).startswith(
                        os.path.realpath(member_root) + os.sep
                    ):
                        return repo.local_path
                    logger.debug(
                        f"[ProjectUtils] repo.local_path {repo.local_path!r} outside "
                        f"member root {member_root!r}; denied"
                    )
    except Exception as e:
        logger.debug(f"DB lookup failed for {project_id}: {e}", exc_info=True)

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
                if repo and repo.sync_status not in REPO_SYNC_INACTIVE_STATUSES:
                    return repo

            # Otherwise, query by project_id among active repos.
            stmt = (
                select(Repository)
                .where(Repository.project_id == project_id)
                .where(Repository.sync_status.notin_(REPO_SYNC_INACTIVE_STATUSES))
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
        logger.warning(
            f"[ProjectUtils] Failed to resolve project_id {project_id} to repo: {e}",
            exc_info=True,
        )
        return None
