import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUserOptional, TokenDep, TokenDepOptional
from app.api.responses import ListResponse
from app.api.schemas.projects import (
    BatchImportRequest,
    BatchImportResponse,
    BatchResultItem,
    CreateProjectRequest,
    DetectedProjectItem,
    IgnoreProjectResponse,
    ImportProjectResponse,
    IndexingRequest,
    IndexingRunResponse,
    ProjectDeleteResponse,
    ProjectStatusActivity,
    ProjectStatusResponse,
    UnignoreProjectResponse,
)
from app.core.evocloud import evocloud_manager
from app.core.file import FileTraverser
from app.core.project.local_index import local_project_index
from app.core.project.sync_service import project_sync_service
from app.core.project.utils import (
    get_project_path,
    resolve_project_to_repo,
    write_project_json,
)
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.wiki.service import wiki_service
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database.graph.driver import GraphManager, is_graph_enabled
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.vector import get_vector_store
from app.models import Repository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


def _resolve_project_id(p: dict) -> int | None:
    """Safely resolve project_id from cloud project dict, treating 0 as valid."""
    raw = p.get("project_id")
    resolved = raw if raw is not None else p.get("id")
    return int(resolved) if resolved is not None else None


def _extract_projects(response: dict | list) -> tuple[list, dict | None]:
    """
    Extract projects list from API response.
    Returns: (projects_list, container_dict_to_update or None)
    """
    if isinstance(response, dict):
        if "list" in response:
            return response["list"], response
        if "data" in response and isinstance(response["data"], dict) and "list" in response["data"]:
            return response["data"]["list"], response["data"]
    elif isinstance(response, list):
        return response, None  # Direct list, update by returning new list
    return [], None


def _scan_workspace_projects() -> dict[str, str]:
    """
    Scan WORKSPACE_ROOT directory to find actual local projects using unified traverser.
    Scans 2 levels deep to handle nested projects.
    """
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not workspace_root or not os.path.isdir(workspace_root):
        return {}

    local_projects = {}

    try:
        # Level 1: Direct children of WORKSPACE_ROOT
        for entry in FileTraverser.list_entries(workspace_root):
            if entry.is_dir():
                local_projects[entry.name] = entry.path

                # Level 2: Scan one level deeper for nested projects
                try:
                    for subentry in FileTraverser.list_entries(entry.path):
                        if subentry.is_dir():
                            local_projects[subentry.name] = subentry.path
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[ProjectsAPI] Failed to scan workspace: {e}")

    return local_projects


@router.get("/")
async def get_projects(
    page: int = 1,
    page_size: int = 100,
    filter_type: str | None = None,
    _token: TokenDepOptional = None,
):
    # 1. Fetch from Cloud and extract projects
    res = await evocloud_manager.api.get_projects(page, page_size, token=_token)
    projects, container = _extract_projects(res)

    # 2. Scan WORKSPACE_ROOT for actual local projects
    workspace_projects = _scan_workspace_projects()
    logger.info(f"[ProjectsAPI] Scanned workspace: {len(workspace_projects)} projects found, cloud: {len(projects)} projects, filter: {filter_type}")

    # 3. Build local_status_map by matching cloud projects with workspace directories,
    #    or from DB-linked repos if cloud returns empty.
    local_status_map = {}
    ignored_project_ids = set()

    try:
        async with session_scope() as session:
            # Get all repositories (including those without project_id for matching)
            stmt = select(Repository).where(Repository.sync_status != "IGNORED")
            result = await session.execute(stmt)
            repos = result.scalars().all()

            # Build repo records lookup for DB-linked projects
            repo_by_project_id = {repo.project_id: repo for repo in repos if repo.project_id}

            matched_count = 0

            if projects:
                # Build local project_id -> path map from .evoloop/project.json
                workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
                local_index = local_project_index.refresh(workspace_root) if workspace_root else {}
                # project_id -> repo records for DB-linked projects
                repo_by_project_id = {repo.project_id: repo for repo in repos if repo.project_id}

                for cloud_project in projects:
                    raw_pid = cloud_project.get("project_id")
                    project_id = raw_pid if raw_pid is not None else cloud_project.get("id")
                    project_name = cloud_project.get("name") or cloud_project.get("project_name", "")

                    # Match by local project_id authority only. Never match by name,
                    # because different devices/cloud entries may share basenames.
                    entry = local_index.get(project_id)
                    actual_path = entry.path if entry else None
                    if not actual_path:
                        # No local .evoloop/project.json with this project_id; check DB-linked repo
                        repo = repo_by_project_id.get(project_id)
                        if repo:
                            actual_path = repo.local_path
                    if not actual_path:
                        # Cloud project not linked locally
                        continue

                    matched_count += 1
                    exists = os.path.exists(actual_path)
                    repo = repo_by_project_id.get(project_id)
                    last_indexed_at = repo.last_indexed_at.isoformat() if repo and repo.last_indexed_at else None

                    if repo and repo.project_id == project_id:
                        # Already linked to this cloud project
                        local_status_map[project_id] = {
                            "status": "SYNCED" if exists else "DISCONNECTED",
                            "exists_locally": exists,
                            "local_path": actual_path,
                            "repo_id": repo.id,
                            "indexing_status": repo.indexing_status,
                            "last_indexed_at": last_indexed_at,
                        }
                    elif repo and repo.project_id is None:
                        # Local exists but not linked - update it to link
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
                        # Cloud is authoritative - update local binding to match
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
                        # No local repo record - create one and auto-link
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
                        # Flush to obtain the new repo id while still in session.
                        await session.flush()
                        logger.info(f"[ProjectsAPI] Created and linked new repo for '{project_name}'")
                        local_status_map[project_id] = {
                            "status": "SYNCED",
                            "exists_locally": True,
                            "local_path": actual_path,
                            "repo_id": new_repo.id,
                            "indexing_status": "pending",
                            "last_indexed_at": None,
                        }

                logger.info(f"[ProjectsAPI] Matched {matched_count} cloud projects with local workspace")
            else:
                # Fallback: cloud returned empty, build projects from linked DB repos + workspace scan
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
                                "has_wiki": False,  # Will be updated below
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
                        logger.info(f"[ProjectsAPI] Built {len(projects)} projects from DB fallback")

            # Get explicitly ignored projects
            ignored_stmt = select(Repository).where(
                Repository.project_id.isnot(None),
                Repository.sync_status == "IGNORED"
            )
            ignored_result = await session.execute(ignored_stmt)
            for ignored_repo in ignored_result.scalars().all():
                ignored_project_ids.add(ignored_repo.project_id)

    except Exception as e:
        logger.warning(f"[ProjectsAPI] Failed to fetch local repository status: {e}")
        logger.exception(e)

    # 3. Enrich projects with local status
    for p in projects:
        raw_pid = p.get("project_id")
        pid = raw_pid if raw_pid is not None else p.get("id")
        if pid and pid in local_status_map:
            local_info = local_status_map[pid]
            p["local_status"] = local_info["status"]
            p["exists_locally"] = local_info["exists_locally"]
            p["local_path"] = local_info.get("local_path", "")
            # Use DB indexing_status as fallback if cache doesn't have it
            p["db_indexing_status"] = local_info.get("indexing_status", "pending")
            p["last_indexed_at"] = local_info.get("last_indexed_at")
        else:
            # Cloud project not linked locally
            p["local_status"] = None
            p["exists_locally"] = False
            p["local_path"] = ""
            p["db_indexing_status"] = "not_linked"
            p["last_indexed_at"] = None

    # 3.5. Filter out ignored projects from the cloud list
    # Projects that were linked but then ignored should not appear
    original_count = len(projects)
    projects = [
        p for p in projects if (_resolve_project_id(p)) not in ignored_project_ids
    ]
    filtered_count = original_count - len(projects)
    if filtered_count > 0:
        logger.info(f"[ProjectsAPI] Filtered {filtered_count} ignored projects from cloud list")

    # 3.6. Apply filter_type parameter
    # - "switchable": Projects that exist BOTH in cloud AND locally with valid path
    #   (Intersection: must be in cloud list AND linked locally with existing path)
    # - "cloud_only": Only return cloud projects not linked locally
    # - "disconnected": Only return linked but disconnected projects (path doesn't exist)
    if filter_type:
        original_count = len(projects)
        if filter_type == "switchable":
            # STRICT: Must exist in BOTH cloud AND locally
            # - Must be in local_status_map (linked locally)
            # - Must have exists_locally = True (path exists)
            # - Must NOT be DISCONNECTED
            cloud_project_ids = {_resolve_project_id(p) for p in projects}
            local_linked_ids = set(local_status_map.keys())

            # Find orphaned local repos (local has but cloud doesn't) - should not happen for switchable
            orphaned_local = local_linked_ids - cloud_project_ids
            if orphaned_local:
                logger.warning(f"[ProjectsAPI] Found orphaned local repos not in cloud: {orphaned_local}")

            # Switchable = intersection of cloud and valid local
            valid_local_ids = {
                pid for pid, info in local_status_map.items()
                if info.get("exists_locally") is True and info.get("status") != "DISCONNECTED"
            }
            switchable_ids = cloud_project_ids & valid_local_ids

            projects = [
                p for p in projects if (_resolve_project_id(p)) in switchable_ids
            ]
            logger.info(
                f"[ProjectsAPI] Filtered to switchable projects: {len(projects)} of {original_count} "
                f"(cloud={len(cloud_project_ids)}, valid_local={len(valid_local_ids)}, intersection={len(switchable_ids)})"
            )
        elif filter_type == "cloud_only":
            # STRICT: Cloud only = in cloud list but NOT linked locally
            cloud_project_ids = {_resolve_project_id(p) for p in projects}
            local_linked_ids = set(local_status_map.keys())

            cloud_only_ids = cloud_project_ids - local_linked_ids

            projects = [
                p for p in projects if (_resolve_project_id(p)) in cloud_only_ids
            ]
            logger.info(f"[ProjectsAPI] Filtered to cloud-only projects: {len(projects)} of {original_count}")
        elif filter_type == "disconnected":
            # STRICT: Disconnected = in BOTH cloud AND local, but path doesn't exist
            cloud_project_ids = {_resolve_project_id(p) for p in projects}

            disconnected_ids = {
                pid for pid, info in local_status_map.items()
                if info.get("status") == "DISCONNECTED"
            }
            # Intersection: must be in cloud AND disconnected locally
            disconnected_ids = cloud_project_ids & disconnected_ids

            projects = [
                p for p in projects if (_resolve_project_id(p)) in disconnected_ids
            ]
            logger.info(f"[ProjectsAPI] Filtered to disconnected projects: {len(projects)} of {original_count}")

    logger.info(f"[ProjectsAPI] Final response: {len(projects)} projects")

    # Collect IDs for batch DB query (only for locally existing projects)
    project_ids = []
    for p in projects:
        pid = _resolve_project_id(p)
        # Only query system status if project exists locally
        if pid and p.get("exists_locally"):
            project_ids.append(pid)

    # Batch check wiki existence
    projects_with_wiki = set()
    try:
        projects_with_wiki = wiki_service.get_projects_with_wiki(project_ids)
    except Exception as e:
        logger.warning(f"Failed to check wiki existence: {e}")

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

    # Execute batch
    pipeline_results = await pipe.execute()

    # Map results back to projects
    status_map = {}
    for i, pid in enumerate(project_keys):
        # Each project has 3 keys in pipeline
        wiki_res = pipeline_results[i * 3]
        idx_res = pipeline_results[i * 3 + 1]
        sum_res = pipeline_results[i * 3 + 2]

        status_map[pid] = {
            "wiki_status": wiki_res.get("status", "idle") if wiki_res else "idle",
            "indexing_status": idx_res.get("status", "idle") if idx_res else "idle",
            "summarization_status": sum_res.get("status", "idle") if sum_res else "idle",
        }

    # Enrich loop
    for p in projects:
        pid = _resolve_project_id(p)
        if pid:
            # Local Status from map
            statuses = status_map.get(pid, {
                "wiki_status": "idle",
                "indexing_status": "idle",
                "summarization_status": "idle",
            })
            p.update(statuses)

            # Wiki Existence (from DB)
            p["has_wiki"] = pid in projects_with_wiki

    # Update the response with filtered projects
    # Write back to the original container, or return new list if no container
    if container is not None:
        container["list"] = projects
        container["total"] = len(projects)
        return res
    return projects


@router.get("/current")
async def get_current_project(_token: TokenDep):
    """
    Get current project from Cloud (User's focus on Web/Mobile).
    Also returns Local Focus if configured.
    """
    cloud_res = await evocloud_manager.api.get_current_project(token=_token)
    # Add local context if needed
    # ...
    return cloud_res


@router.post("/")
async def create_project(req: CreateProjectRequest, _token: TokenDep):
    """Create a new project directory and sync to Member Center."""
    root_dir = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not root_dir:
        raise HTTPException(500, "WORKSPACE_ROOT not configured")

    project_path = os.path.join(root_dir, req.name)
    if os.path.exists(project_path):
        raise HTTPException(400, "Project already exists")

    try:
        os.makedirs(project_path, exist_ok=True)
        # Create skeleton .evoloop/project.json (project_id will be backfilled after cloud sync)
        meta_dir = os.path.join(project_path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        description = "Created via EvoLoop"
        from app.core.hitl.policies import DEFAULT_SENSITIVE_PATTERNS
        skeleton = {
            "name": req.name,
            "description": description,
            "project_id": None,
            "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
            "authorized_paths": [],
        }
        with open(os.path.join(meta_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(skeleton, f, indent=2, ensure_ascii=False)

        # Sync with Member Center
        res = await evocloud_manager.api.create_project(req.name, description, project_path, token=_token)
        if res.get("code") != 0:
            logger.warning(f"Failed to sync project creation to Member Center: {res}")
            raise HTTPException(500, f"Failed to create project in cloud: {res.get('message')}")

        # Invalidate cache to ensure fresh data
        evocloud_manager.invalidate_projects_cache()

        # Re-scan to get ID/Color
        projects = await evocloud_manager.scan_projects()
        new_proj = next((p for p in projects if p["name"] == req.name), None)
        if not new_proj:
            raise HTTPException(500, "Project created in cloud but ID could not be resolved")

        project_id = _resolve_project_id(new_proj)
        if project_id is not None:
            write_project_json(project_path, {"project_id": project_id})

        return new_proj
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(500, str(e))


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(project_id: int):
    """
    Get real-time status of system tasks (Indexing, Summarization) for a project.

    The authoritative local status is stored per repository. This endpoint resolves
    the project to its active local repo and returns repo-level status under the
    project API surface.
    """
    repo = await resolve_project_to_repo(project_id)
    repo_id = repo.id if repo else None

    if repo_id is None:
        return ProjectStatusResponse(
            indexing=ProjectStatusActivity.model_validate({"status": "idle"}),
            summarization=ProjectStatusActivity.model_validate({"status": "idle"}),
            wiki=ProjectStatusActivity.model_validate({"status": "idle"}),
        )

    indexing_key = f"sys:{repo_id}:indexing"
    summarization_key = f"sys:{repo_id}:summarization"
    wiki_key = f"sys:{repo_id}:wiki"

    pipe = cache.pipeline()
    pipe.hgetall(indexing_key)
    pipe.hgetall(summarization_key)
    pipe.hgetall(wiki_key)

    results = await pipe.execute()

    # Helper to parse activity data (mirrors get_activity logic but for raw hgetall results)
    def parse_act(data):
        if not data:
            return {"status": "idle"}
        try:
            return {
                "status": data.get("status", "idle"),
                "updated_at": float(data.get("updated_at", 0)),
                "agent_state": json.loads(data.get("agent_state", "{}")),
                "steps": json.loads(data.get("steps", "[]")),
            }
        except Exception:
            return {"status": "idle"}

    return ProjectStatusResponse(
        indexing=ProjectStatusActivity.model_validate(parse_act(results[0])),
        summarization=ProjectStatusActivity.model_validate(parse_act(results[1])),
        wiki=ProjectStatusActivity.model_validate(parse_act(results[2])),
    )


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(project_id: int, _token: TokenDep):
    """Delete a project from Cloud and clean up all local associated data."""
    try:
        # 1. Delete from Cloud
        res = await evocloud_manager.api.delete_project(project_id, token=_token)
        if res.get("code") != 0:
            raise HTTPException(500, f"Failed to delete project: {res.get('message')}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project from cloud: {e}")
        raise HTTPException(500, str(e))

    # 2. Clean up local data (best effort - don't fail the API if cleanup fails)
    try:
        project_path = await get_project_path(project_id)
        repos: list[Repository] = []
        async with session_scope() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repos = list(result.scalars().all())

        if not repos:
            logger.info(f"[ProjectsAPI] No local repository found for project {project_id}")
        else:
            for repo in repos:
                # Resolve the actual local path; fall back to the stored local_path if resolution fails.
                local_project_path = project_path or repo.local_path
                # Stop file watching
                if local_project_path:
                    await indexing_manager.stop_watching(local_project_path)

                # Clear cache keys keyed by repo_id
                try:
                    pipe = cache.pipeline()
                    pipe.delete(f"sys:{repo.id}:indexing")
                    pipe.delete(f"sys:{repo.id}:summarization")
                    pipe.delete(f"sys:{repo.id}:wiki")
                    pipe.delete(f"indexing:cancel:{repo.id}")
                    await pipe.execute()
                except Exception as e:
                    logger.warning(f"[ProjectsAPI] Failed to clear cache for repo {repo.id}: {e}")

                if is_graph_enabled():
                    try:
                        driver = GraphManager.get_driver(project_path=local_project_path)
                        await driver.execute_query(
                            """
                            MATCH (f:File {project_id: $pid})
                            OPTIONAL MATCH (f)-[:CONTAINS]->(e)
                            DETACH DELETE e
                            DETACH DELETE f
                            """,
                            pid=project_id,
                        )
                    except NotImplementedError:
                        logger.debug("[ProjectsAPI] Graph cleanup skipped (not supported in embedded mode)")
                    except Exception as e:
                        logger.warning(f"[ProjectsAPI] Failed to cleanup graph data for project {project_id}: {e}")

                # Clean up vector store data (if enabled)
                try:
                    vector_store = get_vector_store(project_path=local_project_path)
                    # Delete all chunks for this repository
                    await asyncio.to_thread(vector_store.delete_by_repository, str(repo.id))
                except Exception as e:
                    logger.warning(f"[ProjectsAPI] Failed to cleanup vector store for repo {repo.id}: {e}")

            # Delete Repositories (cascade deletes SourceFile, CodeChunk, CodeEntity, CodeRelation)
            async with session_scope() as session:
                for repo in repos:
                    repo_to_delete = await session.get(Repository, repo.id)
                    if repo_to_delete:
                        await session.delete(repo_to_delete)
                        logger.info(f"[ProjectsAPI] Deleted local repository and all associated data for repo {repo.id}")

    except Exception as e:
        logger.error(f"[ProjectsAPI] Failed to cleanup local data for project {project_id}: {e}")

    evocloud_manager.invalidate_projects_cache()
    return ProjectDeleteResponse(status="success", id=project_id)


@router.post("/indexing/run", response_model=IndexingRunResponse)
async def run_indexing_endpoint(req: IndexingRequest):
    """
    Trigger full indexing for a project (Celery Dispatch).
    """
    indexing_manager.dispatch_full_index(req.project_id)
    return IndexingRunResponse(status="queued", project_id=req.project_id)


# ============================================================================
# Project Import Management Endpoints
# ============================================================================


@router.post("/scan", response_model=ListResponse[DetectedProjectItem])
async def scan_workspace_projects_endpoint(_token: TokenDep):
    """
    Manually scan WORKSPACE_ROOT for new projects.
    Forces reconciliation even if automatic discovery is disabled.
    """
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not workspace_root:
        raise HTTPException(400, "WORKSPACE_ROOT not configured. Please set it in Settings.")

    try:
        # Force reconciliation to find new projects
        await project_sync_service.reconcile_projects(workspace_root, force=True)

        # Return currently detected projects
        repos = await project_sync_service.get_detected_projects()
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except Exception as e:
        logger.error(f"Failed to scan workspace: {e}")
        raise HTTPException(500, f"Scan failed: {str(e)}")


@router.get("/detected", response_model=ListResponse[DetectedProjectItem])
async def get_detected_projects(
    force: bool = False,
    _token: TokenDepOptional = None,
    current_user: CurrentUserOptional = None,
):
    """
    Get all newly detected projects awaiting user confirmation.

    Returns projects with sync_status="DETECTED" that need to be imported or ignored.

    Note: Returns empty list if project discovery is disabled via configuration,
    unless force=True is specified.
    """
    if not force:
        # Check if project discovery is enabled via System Config (DB)
        config_value = SystemConfigService.get_value("PROJECT_DISCOVERY_ENABLED")
        if config_value is not None and config_value.lower() not in (
            "true",
            "1",
            "yes",
            "on",
        ):
            logger.debug("[ProjectsAPI] Project discovery disabled by system config, returning empty detected list")
            return {"data": []}

    try:
        member_id = current_user.id if current_user else None
        repos = await project_sync_service.get_detected_projects(member_id=member_id)
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except Exception as e:
        logger.error(f"Failed to get detected projects: {e}")
        raise HTTPException(500, f"Failed to get detected projects: {str(e)}")


@router.post("/{repo_id}/import", response_model=ImportProjectResponse)
async def import_detected_project(repo_id: int, _token: TokenDep):
    """
    Import a detected project (user confirmed).

    This will:
    1. Update project status to PENDING_CREATION
    2. Start file watching and indexing
    3. Dispatch cloud sync task
    """
    try:
        repo = await project_sync_service.import_project(repo_id)
        return ImportProjectResponse(
            status="success",
            repo_id=repo.id,
            name=repo.name,
            message=f"Project '{repo.name}' imported successfully",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to import project {repo_id}: {e}")
        raise HTTPException(500, f"Failed to import project: {str(e)}")


@router.post("/{repo_id}/ignore", response_model=IgnoreProjectResponse)
async def ignore_detected_project(repo_id: int, _token: TokenDep):
    """
    Ignore a detected project (user chose not to import).

    Marks the project as IGNORED. Can be restored later.
    """
    try:
        await project_sync_service.ignore_project(repo_id)
        return IgnoreProjectResponse(status="ignored", repo_id=repo_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to ignore project {repo_id}: {e}")
        raise HTTPException(500, f"Failed to ignore project: {str(e)}")


@router.get("/ignored", response_model=ListResponse[DetectedProjectItem])
async def get_ignored_projects(
    _token: TokenDep,
    current_user: CurrentUserOptional = None,
):
    """
    Get all ignored projects.

    These projects can be restored (un-ignored) later.
    """
    try:
        member_id = current_user.id if current_user else None
        repos = await project_sync_service.get_ignored_projects(member_id=member_id)
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except Exception as e:
        logger.error(f"Failed to get ignored projects: {e}")
        raise HTTPException(500, f"Failed to get ignored projects: {str(e)}")


@router.post("/{repo_id}/unignore", response_model=UnignoreProjectResponse)
async def unignore_project(repo_id: int, _token: TokenDep):
    """
    Restore an ignored project to detected status.

    Allows the project to be imported.
    """
    try:
        repo = await project_sync_service.unignore_project(repo_id)
        return UnignoreProjectResponse(
            status="restored",
            repo_id=repo.id,
            name=repo.name,
            message=f"Project '{repo.name}' restored to detected state",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to unignore project {repo_id}: {e}")
        raise HTTPException(500, f"Failed to restore project: {str(e)}")


@router.post("/batch/import", response_model=BatchImportResponse)
async def batch_import_projects(req: BatchImportRequest, _token: TokenDep):
    """
    Import multiple detected projects in batch.

    This will:
    1. Import each project sequentially
    2. Return summary of successes and failures
    """
    results: dict[str, list[BatchResultItem]] = {
        "success": [],
        "failed": [],
    }

    for repo_id in req.repo_ids:
        try:
            repo = await project_sync_service.import_project(repo_id)
            results["success"].append(BatchResultItem(repo_id=repo.id, name=repo.name))
        except ValueError as e:
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))
        except Exception as e:
            logger.error(f"Failed to import project {repo_id}: {e}")
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))

    return BatchImportResponse(
        status="completed",
        summary=f"Imported {len(results['success'])} of {len(req.repo_ids)} projects",
        results=results,
    )


@router.post("/batch/ignore", response_model=BatchImportResponse)
async def batch_ignore_projects(req: BatchImportRequest, _token: TokenDep):
    """
    Ignore multiple detected projects in batch.
    """
    results: dict[str, list[BatchResultItem]] = {
        "success": [],
        "failed": [],
    }

    for repo_id in req.repo_ids:
        try:
            await project_sync_service.ignore_project(repo_id)
            results["success"].append(BatchResultItem(repo_id=repo_id))
        except ValueError as e:
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))
        except Exception as e:
            logger.error(f"Failed to ignore project {repo_id}: {e}")
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))

    return BatchImportResponse(
        status="completed",
        summary=f"Ignored {len(results['success'])} of {len(req.repo_ids)} projects",
        results=results,
    )
