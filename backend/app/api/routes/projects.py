import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep, TokenDepOptional
from app.core.config import settings
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.service import project_context_manager
from app.infrastructure.external.evocloud import evocloud_client

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
    return await evocloud_client.get_projects(page, page_size)


@router.get("/current")
async def get_current_project(_token: TokenDep):
    """
    Get current project from Cloud (User's focus on Web/Mobile).
    Also returns Local Focus if configured.
    """
    cloud_res = await evocloud_client.get_current_project()
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
        res = await evocloud_client.create_project(req.name, "Created via EvoLoop", project_path)
        if res.get("code") != 0:
            logger.warning(f"Failed to sync project creation to Member Center: {res}")

        # Re-scan to get ID/Color
        projects = await project_context_manager.scan_projects()
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
    from app.core.monitoring.activity import activity_monitor

    indexing_key = f"sys:{project_id}:indexing"
    summarization_key = f"sys:{project_id}:summarization"

    indexing = await activity_monitor.get_activity(indexing_key)
    summarization = await activity_monitor.get_activity(summarization_key)

    return {"indexing": indexing, "summarization": summarization}


@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """Delete a project (Unlink from Member Center)."""
    try:
        res = await evocloud_client.delete_project(project_id)
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
