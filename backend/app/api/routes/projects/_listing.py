"""
Projects listing endpoint — get_projects with status enrichment.
"""

import logging
import os

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import TokenDepOptional
from app.core.evocloud import evocloud_manager
from app.core.file import FileTraverser
from app.core.project.local_index import local_project_index
from app.domain.wiki.service import wiki_service
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database import session_scope as session_scope
from app.models import Repository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_project_id(p: dict) -> int | None:
    raw = p.get("project_id")
    resolved = raw if raw is not None else p.get("id")
    return int(resolved) if resolved is not None else None


def _extract_projects(response: dict | list) -> tuple[list, dict | None]:
    if isinstance(response, dict):
        if "list" in response:
            return response["list"], response
        if "data" in response and isinstance(response["data"], dict) and "list" in response["data"]:
            return response["data"]["list"], response["data"]
    elif isinstance(response, list):
        return response, None
    return [], None


def _scan_workspace_projects() -> dict[str, str]:
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not workspace_root or not os.path.isdir(workspace_root):
        return {}

    local_projects = {}
    try:
        for entry in FileTraverser.list_entries(workspace_root):
            if entry.is_dir():
                local_projects[entry.name] = entry.path
                try:
                    for subentry in FileTraverser.list_entries(entry.path):
                        if subentry.is_dir():
                            local_projects[subentry.name] = subentry.path
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)
    except Exception as e:
        logger.warning("[ProjectsAPI] Failed to scan workspace: %s", e)

    return local_projects


@router.get("/")
async def get_projects(
    page: int = 1,
    page_size: int = 100,
    filter_type: str | None = None,
    _token: TokenDepOptional = None,
):
    res = await evocloud_manager.api.get_projects(page, page_size, token=_token)
    projects, container = _extract_projects(res)
    workspace_projects = _scan_workspace_projects()
    logger.info(
        "[ProjectsAPI] Scanned workspace: %d projects found, cloud: %d projects, filter: %s",
        len(workspace_projects),
        len(projects),
        filter_type,
    )

    local_status_map = {}
    ignored_project_ids = set()

    try:
        async with session_scope() as session:
            stmt = select(Repository).where(Repository.sync_status != "IGNORED")
            result = await session.execute(stmt)
            repos = result.scalars().all()

            matched_count = 0

            if projects:
                workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
                local_index = local_project_index.refresh(workspace_root) if workspace_root else {}
                repo_by_project_id = {repo.project_id: repo for repo in repos if repo.project_id}

                for cloud_project in projects:
                    raw_pid = cloud_project.get("project_id")
                    project_id = raw_pid if raw_pid is not None else cloud_project.get("id")
                    project_name = cloud_project.get("name") or cloud_project.get("project_name", "")

                    entry = local_index.get(project_id)
                    actual_path = entry.path if entry else None
                    if not actual_path:
                        repo = repo_by_project_id.get(project_id)
                        if repo:
                            actual_path = repo.local_path
                    if not actual_path:
                        continue

                    matched_count += 1
                    exists = os.path.exists(actual_path)
                    repo = repo_by_project_id.get(project_id)
                    last_indexed_at = repo.last_indexed_at.isoformat() if repo and repo.last_indexed_at else None

                    if repo and repo.project_id == project_id:
                        local_status_map[project_id] = {
                            "status": "SYNCED" if exists else "DISCONNECTED",
                            "exists_locally": exists,
                            "local_path": actual_path,
                            "repo_id": repo.id,
                            "indexing_status": repo.indexing_status,
                            "last_indexed_at": last_indexed_at,
                        }
                    elif repo and repo.project_id is None:
                        repo.project_id = project_id
                        repo.sync_status = "SYNCED"
                        repo.imported_at = utcnow()
                        local_status_map[project_id] = {
                            "status": "SYNCED",
                            "exists_locally": True,
                            "local_path": actual_path,
                            "repo_id": repo.id,
                            "indexing_status": repo.indexing_status,
                            "last_indexed_at": last_indexed_at,
                        }
                    elif repo and repo.project_id != project_id:
                        repo.project_id = project_id
                        repo.sync_status = "SYNCED"
                        repo.imported_at = utcnow()
                        local_status_map[project_id] = {
                            "status": "SYNCED",
                            "exists_locally": True,
                            "local_path": actual_path,
                            "repo_id": repo.id,
                            "indexing_status": repo.indexing_status,
                            "last_indexed_at": last_indexed_at,
                        }
                    else:
                        new_repo = Repository(
                            name=project_name,
                            url="local",
                            local_path=actual_path,
                            sync_status="SYNCED",
                            indexing_status="pending",
                            detected_at=utcnow(),
                            imported_at=utcnow(),
                            project_id=project_id,
                        )
                        session.add(new_repo)
                        await session.flush()
                        logger.info("[ProjectsAPI] Created and linked new repo for '%s'", project_name)
                        local_status_map[project_id] = {
                            "status": "SYNCED",
                            "exists_locally": True,
                            "local_path": actual_path,
                            "repo_id": new_repo.id,
                            "indexing_status": "pending",
                            "last_indexed_at": None,
                        }

                logger.info("[ProjectsAPI] Matched %d cloud projects with local workspace", matched_count)
            else:
                logger.warning("[ProjectsAPI] Cloud returned empty project list, using DB fallback for linked projects")
                workspace_projects = _scan_workspace_projects()
                if filter_type == "switchable":
                    for repo in repos:
                        if repo.project_id and repo.name and repo.name in workspace_projects:
                            actual_path = workspace_projects[repo.name]
                            last_indexed_at = repo.last_indexed_at.isoformat() if repo.last_indexed_at else None
                            if os.path.exists(actual_path):
                                projects.append({
                                    "project_id": repo.project_id,
                                    "name": repo.name,
                                    "project_name": repo.name,
                                    "project_desc": repo.description or "",
                                    "description": repo.description or "",
                                    "external_path": actual_path,
                                    "status": 1,
                                    "status_text": "正常",
                                    "local_status": "SYNCED",
                                    "exists_locally": True,
                                    "local_path": actual_path,
                                    "db_indexing_status": repo.indexing_status,
                                    "last_indexed_at": last_indexed_at,
                                    "has_wiki": False,
                                })
                                local_status_map[repo.project_id] = {
                                    "status": "SYNCED",
                                    "exists_locally": True,
                                    "local_path": actual_path,
                                    "repo_id": repo.id,
                                    "indexing_status": repo.indexing_status,
                                    "last_indexed_at": last_indexed_at,
                                }
                    if projects:
                        logger.info("[ProjectsAPI] Built %d projects from DB fallback", len(projects))

            ignored_stmt = select(Repository).where(
                Repository.project_id.isnot(None),
                Repository.sync_status == "IGNORED"
            )
            ignored_result = await session.execute(ignored_stmt)
            for ignored_repo in ignored_result.scalars().all():
                ignored_project_ids.add(ignored_repo.project_id)

    except Exception as e:
        logger.warning("[ProjectsAPI] Failed to fetch local repository status: %s", e)
        logger.exception(e)

    for p in projects:
        raw_pid = p.get("project_id")
        pid = raw_pid if raw_pid is not None else p.get("id")
        if pid and pid in local_status_map:
            local_info = local_status_map[pid]
            p["local_status"] = local_info["status"]
            p["exists_locally"] = local_info["exists_locally"]
            p["local_path"] = local_info.get("local_path", "")
            p["db_indexing_status"] = local_info.get("indexing_status", "pending")
            p["last_indexed_at"] = local_info.get("last_indexed_at")
        else:
            p["local_status"] = None
            p["exists_locally"] = False
            p["local_path"] = ""
            p["db_indexing_status"] = "not_linked"
            p["last_indexed_at"] = None

    original_count = len(projects)
    projects = [p for p in projects if (_resolve_project_id(p)) not in ignored_project_ids]
    filtered_count = original_count - len(projects)
    if filtered_count > 0:
        logger.info("[ProjectsAPI] Filtered %d ignored projects from cloud list", filtered_count)

    if filter_type:
        original_count = len(projects)
        if filter_type == "switchable":
            cloud_project_ids = {_resolve_project_id(p) for p in projects}
            local_linked_ids = set(local_status_map.keys())

            orphaned_local = local_linked_ids - cloud_project_ids
            if orphaned_local:
                logger.warning("[ProjectsAPI] Found orphaned local repos not in cloud: %s", orphaned_local)

            valid_local_ids = {
                pid for pid, info in local_status_map.items()
                if info.get("exists_locally") is True and info.get("status") != "DISCONNECTED"
            }
            switchable_ids = cloud_project_ids & valid_local_ids

            projects = [p for p in projects if (_resolve_project_id(p)) in switchable_ids]
            logger.info(
                "[ProjectsAPI] Filtered to switchable projects: %d of %d (cloud=%d, valid_local=%d, intersection=%d)",
                len(projects),
                original_count,
                len(cloud_project_ids),
                len(valid_local_ids),
                len(switchable_ids),
            )
        elif filter_type == "cloud_only":
            cloud_project_ids = {_resolve_project_id(p) for p in projects}
            local_linked_ids = set(local_status_map.keys())
            cloud_only_ids = cloud_project_ids - local_linked_ids
            projects = [p for p in projects if (_resolve_project_id(p)) in cloud_only_ids]
            logger.info("[ProjectsAPI] Filtered to cloud-only projects: %d of %d", len(projects), original_count)
        elif filter_type == "disconnected":
            cloud_project_ids = {_resolve_project_id(p) for p in projects}
            disconnected_ids = {
                pid for pid, info in local_status_map.items()
                if info.get("status") == "DISCONNECTED"
            }
            disconnected_ids = cloud_project_ids & disconnected_ids
            projects = [p for p in projects if (_resolve_project_id(p)) in disconnected_ids]
            logger.info("[ProjectsAPI] Filtered to disconnected projects: %d of %d", len(projects), original_count)

    logger.info("[ProjectsAPI] Final response: %d projects", len(projects))

    project_ids = []
    for p in projects:
        pid = _resolve_project_id(p)
        if pid and p.get("exists_locally"):
            project_ids.append(pid)

    projects_with_wiki = set()
    try:
        projects_with_wiki = wiki_service.get_projects_with_wiki(project_ids)
    except Exception as e:
        logger.warning("Failed to check wiki existence: %s", e)

    pipe = cache.pipeline()
    project_keys = []
    for p in projects:
        pid = _resolve_project_id(p)
        if pid and pid in local_status_map:
            repo_id = local_status_map[pid].get("repo_id")
            if repo_id:
                keys = [
                    f"sys:{repo_id}:wiki",
                    f"sys:{repo_id}:indexing",
                    f"sys:{repo_id}:summarization",
                ]
                project_keys.append(pid)
                for k in keys:
                    pipe.hgetall(k)

    pipeline_results = await pipe.execute()

    status_map = {}
    for i, pid in enumerate(project_keys):
        wiki_res = pipeline_results[i * 3]
        idx_res = pipeline_results[i * 3 + 1]
        sum_res = pipeline_results[i * 3 + 2]

        status_map[pid] = {
            "wiki_status": wiki_res.get("status", "idle") if wiki_res else "idle",
            "indexing_status": idx_res.get("status", "idle") if idx_res else "idle",
            "summarization_status": sum_res.get("status", "idle") if sum_res else "idle",
        }

    for p in projects:
        pid = _resolve_project_id(p)
        if pid:
            statuses = status_map.get(pid, {
                "wiki_status": "idle",
                "indexing_status": "idle",
                "summarization_status": "idle",
            })
            p.update(statuses)
            p["has_wiki"] = pid in projects_with_wiki

    if container is not None:
        container["list"] = projects
        container["total"] = len(projects)
        return res
    return projects
