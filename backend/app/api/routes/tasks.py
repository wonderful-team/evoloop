from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel

from app.infrastructure.external.imagicbox import imagicbox_client
from app.logging import logger

router = APIRouter()

# --- Helper ---
def get_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return authorization

# --- Pydantic Models for Request Body ---

class TaskCreateRequest(BaseModel):
    project_id: int
    task_title: str
    task_desc: Optional[str] = ""
    # Optional fields that match the AI Enhanced structure
    priority: int = 2
    match_score: Optional[float] = None
    relevance_analysis: Optional[str] = None
    key_modules: Optional[Any] = None # List or Str
    technical_challenges: Optional[Any] = None
    implementation_complexity: Optional[str] = None
    deliverables: Optional[Any] = None

class TaskUpdateRequest(BaseModel):
    task_title: Optional[str] = None
    task_desc: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[int] = None
    progress: Optional[int] = None
    # AI fields are also updateable
    match_score: Optional[float] = None
    relevance_analysis: Optional[str] = None
    key_modules: Optional[Any] = None
    technical_challenges: Optional[Any] = None
    implementation_complexity: Optional[str] = None
    deliverables: Optional[Any] = None

class TaskStatusUpdate(BaseModel):
    status: int
    progress: Optional[int] = 0

# --- Routes ---

@router.get("/")
async def get_project_tasks(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    status: Optional[int] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Get a list of tasks for a specific project.
    """
    token = get_token(authorization)
    res = imagicbox_client.get_project_tasks(
        project_id=project_id, 
        page=page, 
        page_size=page_size, 
        status=status,
        token=token
    )
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get tasks"))
    
    return res.get("data", {})

@router.get("/{task_id}")
async def get_task_detail(task_id: int, authorization: Optional[str] = Header(None)):
    """
    Get details of a specific task.
    """
    token = get_token(authorization)
    res = imagicbox_client.get_task_detail(task_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get task detail"))
    
    return res.get("data", {})

@router.post("/")
async def create_task(req: TaskCreateRequest, authorization: Optional[str] = Header(None)):
    """
    Create a new task.
    """
    token = get_token(authorization)
    # Convert Pydantic model to dict, exclude None to let backend handle defaults
    data = req.model_dump(exclude_none=True)
    
    res = imagicbox_client.create_task(data, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to create task"))
    
    return res

@router.put("/{task_id}")
async def update_task(task_id: int, req: TaskUpdateRequest, authorization: Optional[str] = Header(None)):
    """
    Update a task.
    """
    token = get_token(authorization)
    data = req.model_dump(exclude_none=True)
    data['task_id'] = task_id # Ensure ID is passed if needed by backend, though URL param usually sufficient for routing
    
    res = imagicbox_client.update_task(task_id, data, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to update task"))
    
    return res

@router.delete("/{task_id}")
async def delete_task(task_id: int, authorization: Optional[str] = Header(None)):
    """
    Delete a task.
    """
    token = get_token(authorization)
    res = imagicbox_client.delete_task(task_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to delete task"))
    
    return res

@router.put("/{task_id}/status")
async def update_task_status_endpoint(task_id: int, req: TaskStatusUpdate, authorization: Optional[str] = Header(None)):
    """
    Update task status and progress.
    """
    token = get_token(authorization)
    res = imagicbox_client.update_task_status(task_id, req.status, req.progress, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to update task status"))
    
    return res
