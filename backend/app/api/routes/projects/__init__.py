"""
Projects API Routes — package with sub-routers.

Routes are split by functional domain:
- _listing: project listing and status enrichment
- _imports: project import management (scan, detect, import, ignore)
- _profiles: project profile discovery (Agent-driven via Skill system)
- _modules: budget, timesheet, statistics (included separately at /project-modules)
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import TokenDep
from app.api.schemas.projects import (
    CreateProjectRequest,
    IndexingRequest,
    IndexingRunResponse,
    ProjectDeleteResponse,
    ProjectStatusActivity,
    ProjectStatusResponse,
)
from app.core.evocloud import evocloud_manager
from app.core.hitl.policies import DEFAULT_SENSITIVE_PATTERNS
from app.core.project.utils import (
    get_project_path,
    resolve_project_to_repo,
    write_project_json,
)
from app.domain.codebase.indexing.manager import indexing_manager
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database import session_scope
from app.infrastructure.database.vector import get_vector_store
from app.models import Repository

from ._imports import router as imports_router
from ._listing import router as listing_router
from ._modules import router as modules_router  # noqa: F401 — re-export for main.py
from ._profiles import router as profiles_router

logger = logging.getLogger(__name__)

# fmt: off
router = APIRouter()
router.include_router(listing_router)
router.include_router(imports_router)
router.include_router(profiles_router)
# fmt: on


__all__ = ["router", "modules_router"]


def _resolve_project_id(p: dict) -> int | None:
    raw = p.get("project_id")
    resolved = raw if raw is not None else p.get("id")
    return int(resolved) if resolved is not None else None


@router.get("/current")
async def get_current_project(_token: TokenDep):
    cloud_res = await evocloud_manager.api.get_current_project(token=_token)
    return cloud_res


@router.post("/")
async def create_project(req: CreateProjectRequest, _token: TokenDep):
    root_dir = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not root_dir:
        raise HTTPException(500, "WORKSPACE_ROOT not configured")

    project_path = os.path.join(root_dir, req.name)
    if os.path.exists(project_path):
        raise HTTPException(400, "Project already exists")

    try:
        os.makedirs(project_path, exist_ok=True)
        meta_dir = os.path.join(project_path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        description = "Created via EvoLoop"
        skeleton = {
            "name": req.name,
            "description": description,
            "project_id": None,
            "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
            "authorized_paths": [],
        }
        with open(os.path.join(meta_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(skeleton, f, indent=2, ensure_ascii=False)

        res = await evocloud_manager.api.create_project(req.name, description, project_path, token=_token)
        if res.get("code") != 0:
            logger.warning("Failed to sync project creation to Member Center: %s", res)
            raise HTTPException(500, f"Failed to create project in cloud: {res.get('message')}")

        evocloud_manager.invalidate_projects_cache()

        projects = await evocloud_manager.scan_projects()
        new_proj = next((p for p in projects if p["name"] == req.name), None)
        if not new_proj:
            raise HTTPException(500, "Project created in cloud but ID could not be resolved")

        project_id = _resolve_project_id(new_proj)
        if project_id is not None:
            write_project_json(project_path, {"project_id": project_id})

        return new_proj
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to create project: %s", e)
        raise HTTPException(500, str(e))


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(project_id: int):
    repo = await resolve_project_to_repo(project_id)
    repo_id = repo.id if repo else None

    if repo_id is None:
        return ProjectStatusResponse(
            indexing=ProjectStatusActivity.model_validate({"status": "idle"}),
            summarization=ProjectStatusActivity.model_validate({"status": "idle"}),
            wiki=ProjectStatusActivity.model_validate({"status": "idle"}),
        )

    pipe = cache.pipeline()
    pipe.hgetall(f"sys:{repo_id}:indexing")
    pipe.hgetall(f"sys:{repo_id}:summarization")
    pipe.hgetall(f"sys:{repo_id}:wiki")

    results = await pipe.execute()

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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            return {"status": "idle"}

    return ProjectStatusResponse(
        indexing=ProjectStatusActivity.model_validate(parse_act(results[0])),
        summarization=ProjectStatusActivity.model_validate(parse_act(results[1])),
        wiki=ProjectStatusActivity.model_validate(parse_act(results[2])),
    )


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(project_id: int, _token: TokenDep):
    try:
        res = await evocloud_manager.api.delete_project(project_id, token=_token)
        if res.get("code") != 0:
            raise HTTPException(500, f"Failed to delete project: {res.get('message')}")
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to delete project from cloud: %s", e)
        raise HTTPException(500, str(e))

    try:
        project_path = await get_project_path(project_id)
        repos: list[Repository] = []
        async with session_scope() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repos = list(result.scalars().all())

        if not repos:
            logger.info("[ProjectsAPI] No local repository found for project %d", project_id)
        else:
            for repo in repos:
                local_project_path = project_path or repo.local_path
                if local_project_path:
                    await indexing_manager.stop_watching(local_project_path)

                try:
                    pipe = cache.pipeline()
                    pipe.delete(f"sys:{repo.id}:indexing")
                    pipe.delete(f"sys:{repo.id}:summarization")
                    pipe.delete(f"sys:{repo.id}:wiki")
                    pipe.delete(f"indexing:cancel:{repo.id}")
                    await pipe.execute()
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning("[ProjectsAPI] Failed to clear cache for repo %d: %s", repo.id, e)

                try:
                    vector_store = get_vector_store(project_path=local_project_path)
                    await asyncio.to_thread(vector_store.delete_by_repository, str(repo.id))
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning("[ProjectsAPI] Failed to cleanup vector store for repo %d: %s", repo.id, e)

            async with session_scope() as session:
                for repo in repos:
                    repo_to_delete = await session.get(Repository, repo.id)
                    if repo_to_delete:
                        await session.delete(repo_to_delete)
                        logger.info("[ProjectsAPI] Deleted local repository and all associated data for repo %d", repo.id)

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("[ProjectsAPI] Failed to cleanup local data for project %d: %s", project_id, e)

    evocloud_manager.invalidate_projects_cache()
    return ProjectDeleteResponse(status="success", id=project_id)


@router.post("/indexing/run", response_model=IndexingRunResponse)
async def run_indexing_endpoint(req: IndexingRequest):
    indexing_manager.dispatch_full_index(req.project_id)
    return IndexingRunResponse(status="queued", project_id=req.project_id)
