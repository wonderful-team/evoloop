import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep, TokenDepOptional
from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.domain.codebase.indexing.manager import indexing_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


class IndexingRequest(BaseModel):
    project_id: int


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    path: str


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    path: str | None = None


@router.get("/")
async def get_projects(page: int = 1, page_size: int = 100, _token: TokenDepOptional = None):
    # 1. Fetch from Cloud
    res = await evocloud_manager.api.get_projects(page, page_size)

    # Check structure. Usually it returns dict or list.
    # evocloud_manager.api usually returns { "list": [...], "total": ... } or [...]
    # We need to handle safely.
    projects = []
    if isinstance(res, dict) and "list" in res:
        projects = res["list"]
    elif isinstance(res, list):
        projects = res

    if not projects:
        return res

    # 2. Enrich with Local System Status (Redis) and Wiki Existence (DB)
    from app.domain.wiki.service import wiki_service

    # Collect IDs for batch DB query
    project_ids = []
    for p in projects:
        pid = p.get("project_id") or p.get("id")
        if pid:
            project_ids.append(pid)

    # Batch check wiki existence
    projects_with_wiki = set()
    try:
        projects_with_wiki = wiki_service.get_projects_with_wiki(project_ids)
    except Exception as e:
        logger.warning(f"Failed to check wiki existence: {e}")

    # Batch enrichment for Local System Status (Redis)
    from app.infrastructure.database.redis import redis_client

    pipe = redis_client.pipeline()
    project_keys = []
    for p in projects:
        pid = p.get("project_id") or p.get("id")
        if pid:
            keys = [
                f"sys:{pid}:wiki",
                f"sys:{pid}:indexing",
                f"sys:{pid}:summarization"
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
        wiki_res = pipeline_results[i*3]
        idx_res = pipeline_results[i*3 + 1]
        sum_res = pipeline_results[i*3 + 2]

        status_map[pid] = {
            "wiki_status": wiki_res.get("status", "idle") if wiki_res else "idle",
            "indexing_status": idx_res.get("status", "idle") if idx_res else "idle",
            "summarization_status": sum_res.get("status", "idle") if sum_res else "idle",
        }

    # Enrich loop
    for p in projects:
        pid = p.get("project_id") or p.get("id")
        if pid:
            # Local Status from map
            statuses = status_map.get(pid, {"wiki_status": "idle", "indexing_status": "idle", "summarization_status": "idle"})
            p.update(statuses)

            # Wiki Existence (from DB)
            p["has_wiki"] = pid in projects_with_wiki

    return res


@router.get("/current")
async def get_current_project(_token: TokenDep):
    """
    Get current project from Cloud (User's focus on Web/Mobile).
    Also returns Local Focus if configured.
    """
    cloud_res = await evocloud_manager.api.get_current_project()
    # Add local context if needed
    # ...
    return cloud_res


@router.post("/")
async def create_project(req: CreateProjectRequest, _token: TokenDep):
    """Create a new project directory and sync to Member Center."""
    root_dir = settings.PROJECTS_ROOT
    if not root_dir:
        raise HTTPException(500, "PROJECTS_ROOT not configured")

    project_path = os.path.join(root_dir, req.name)
    if os.path.exists(project_path):
        raise HTTPException(400, "Project already exists")

    try:
        os.makedirs(project_path, exist_ok=True)
        # Create skeleton .evoloop/project.json
        meta_dir = os.path.join(project_path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "project.json"), "w") as f:
            f.write(f'{{"name": "{req.name}", "description": "Created via EvoLoop"}}')

        # Sync with Member Center
        res = await evocloud_manager.api.create_project(req.name, "Created via EvoLoop", project_path)
        if res.get("code") != 0:
            logger.warning(f"Failed to sync project creation to Member Center: {res}")

        # Re-scan to get ID/Color
        projects = await evocloud_manager.scan_projects()
        new_proj = next((p for p in projects if p["name"] == req.name), None)
        return new_proj or {"name": req.name}
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(500, str(e))


@router.get("/{project_id}/status")
async def get_project_status(project_id: int):
    """
    Get real-time status of system tasks (Indexing, Summarization) for a project.
    """

    indexing_key = f"sys:{project_id}:indexing"
    summarization_key = f"sys:{project_id}:summarization"
    wiki_key = f"sys:{project_id}:wiki"

    from app.infrastructure.database.redis import redis_client
    pipe = redis_client.pipeline()
    pipe.hgetall(indexing_key)
    pipe.hgetall(summarization_key)
    pipe.hgetall(wiki_key)

    results = await pipe.execute()

    # Helper to parse activity data (mirrors get_activity logic but for raw hgetall results)
    def parse_act(data):
        if not data: return {"status": "idle"}
        try:
            return {
                "status": data.get("status", "idle"),
                "updated_at": float(data.get("updated_at", 0)),
                "agent_state": json.loads(data.get("agent_state", "{}")),
                "steps": json.loads(data.get("steps", "[]")),
            }
        except: return {"status": "idle"}

    return {
        "indexing": parse_act(results[0]),
        "summarization": parse_act(results[1]),
        "wiki": parse_act(results[2])
    }


@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """Delete a project (Unlink from Member Center)."""
    try:
        res = await evocloud_manager.api.delete_project(project_id)
        if res.get("code") == 0:
            return {"status": "success", "id": project_id}
        else:
            raise HTTPException(500, f"Failed to delete project: {res.get('message')}")
    except Exception as e:
        logger.error(f"Failed to delete project: {e}")
        raise HTTPException(500, str(e))


@router.post("/indexing/run")
async def run_indexing_endpoint(req: IndexingRequest):
    """
    Trigger full indexing for a project (Celery Dispatch).
    """
    indexing_manager.dispatch_full_index(req.project_id)
    return {"status": "queued", "project_id": req.project_id}
