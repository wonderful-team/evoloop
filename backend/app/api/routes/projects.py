from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Any
import os

from app.logging import logger
from app.core.config import settings
from app.domain.project.service import project_context_manager
from app.domain.codebase.indexing.manager import indexing_manager

router = APIRouter()

class CreateProjectRequest(BaseModel):
    name: str

class IndexingRequest(BaseModel):
    project_id: int

@router.get("/")
async def list_projects():
    """List all available projects in the configured root directory."""
    projects = await project_context_manager.scan_projects()
    
    final_projects = []
    for p in projects:
        if "id" in p:
             p["indexing_status"] = indexing_manager.get_project_status(p["id"])
        final_projects.append(p)
    
    return {"count": len(final_projects), "projects": final_projects, "root": project_context_manager.get_working_directory("default")}

@router.get("/current")
async def get_current_project():
    """Get current project from Member Center"""
    from app.infrastructure.external.imagicbox import imagicbox_client
    return await imagicbox_client.get_current_project()

@router.post("/")
async def create_project(req: CreateProjectRequest):
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
            f.write(f'{{"name": "{req.name}", "description": "Created via EvoLoop V3"}}')
            
        # Sync with Member Center
        from app.infrastructure.external.imagicbox import imagicbox_client
        res = await imagicbox_client.create_project(req.name, "Created via EvoLoop V3", project_path)
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
    
    return {
        "indexing": indexing,
        "summarization": summarization
    }

@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """Delete a project (Unlink from Member Center)."""
    try:
        from app.infrastructure.external.imagicbox import imagicbox_client
        res = await imagicbox_client.delete_project(project_id)
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
