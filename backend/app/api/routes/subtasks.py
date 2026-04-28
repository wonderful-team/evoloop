"""
Subtask API Routes.

Provides hierarchical task management for Agent task planning.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.api.deps import TokenDep
from app.api.responses import BaseAPIResponse
from app.domain.project.subtask_service import subtask_service
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid
from app.api.schemas.subtasks import SubtaskCreate, TaskWithSubtasksCreate, TaskProgressUpdate, TaskTreeResponse, ExecutableTaskResponse, TaskCreateResponse, TaskTreeWrapperResponse, NextTaskResponse, TaskFlatResponse, TaskListItem, TaskListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/subtasks", tags=["subtasks"])

# --- Pydantic Models ---

# --- API Routes ---

@router.post("/", response_model=TaskCreateResponse)
async def create_task_with_subtasks(
    project_id: int,
    req: TaskWithSubtasksCreate,
    token: TokenDep = None
):
    """
    Create a parent task with optional subtasks.
    
    This is the main entry for Agent to create hierarchical tasks.
    
    Example:
        {
            "title": "实现用户登录模块",
            "description": "完整的用户登录功能",
            "priority": "high",
            "estimated_hours": 8,
            "subtasks": [
                {"title": "设计数据库表", "estimated_hours": 2},
                {"title": "实现登录API", "estimated_hours": 3},
                {"title": "前端登录页面", "estimated_hours": 3}
            ]
        }
    """
    try:
        # Generate dummy analysis_id if not provided
        analysis_id = req.analysis_id or f"direct-{gen_uuid()}"
        
        task = await subtask_service.create_task_with_subtasks(
            project_id=project_id,
            analysis_id=analysis_id,
            title=req.title,
            description=req.description,
            priority=req.priority,
            estimated_hours=req.estimated_hours,
            subtasks=[s.model_dump() for s in req.subtasks],
            created_by="api"
        )
        
        # Get full tree
        tree = await subtask_service.get_task_tree(task.id)
        
        return TaskCreateResponse(
            success=True,
            message=f"Created task with {len(task.subtasks)} subtasks",
            task=tree
        )
        
    except Exception as e:
        logger.error(f"[SubtasksAPI] Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tree/{task_id}", response_model=TaskTreeWrapperResponse)
async def get_task_tree(
    project_id: int,
    task_id: str,
    max_depth: int = 5,
    token: TokenDep = None
):
    """Get task tree structure."""
    tree = await subtask_service.get_task_tree(task_id, max_depth)
    
    if not tree:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return TaskTreeWrapperResponse(
        success=True,
        task=tree
    )

@router.put("/progress/{task_id}", response_model=BaseAPIResponse)
async def update_task_progress(
    project_id: int,
    task_id: str,
    req: TaskProgressUpdate,
    token: TokenDep = None
):
    """
    Update task progress and propagate to parent.
    
    Example:
        {"status": "completed", "progress": 100, "result": "API implemented successfully"}
    """
    success = await subtask_service.update_task_progress(
        task_id=task_id,
        status=req.status,
        progress=req.progress,
        result=req.result
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return BaseAPIResponse(
        success=True,
        message="Progress updated"
    )

@router.get("/next", response_model=NextTaskResponse)
async def get_next_executable_task(
    project_id: int,
    token: TokenDep = None
):
    """
    Get next task ready for execution.
    Returns first pending subtask in order.
    """
    task = await subtask_service.get_next_executable_task(project_id)
    
    if not task:
        return NextTaskResponse(
            success=True,
            message="No pending tasks",
            task=None
        )
        
    return NextTaskResponse(
        success=True,
        message="",
        task=task
    )

@router.get("/flat/{task_id}", response_model=TaskFlatResponse)
async def flatten_task_tree(
    project_id: int,
    task_id: str,
    token: TokenDep = None
):
    """
    Flatten task tree to execution list.
    Useful for Agent to get sequential execution order.
    """
    flat_list = await subtask_service.flatten_task_tree(task_id)
    
    return TaskFlatResponse(
        success=True,
        count=len(flat_list),
        tasks=flat_list
    )

@router.get("/list", response_model=TaskListResponse)
async def list_root_tasks(
    project_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    token: TokenDep = None
):
    """List root tasks (parent tasks) for a project."""
    from sqlalchemy import select
    from app.domain.project.requirements.models import ProjectRequirementTask
    from app.infrastructure.database.sql.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as session:
        query = select(ProjectRequirementTask).where(
            ProjectRequirementTask.project_id == project_id,
            ProjectRequirementTask.parent_id.is_(None)
        ).order_by(ProjectRequirementTask.created_at.desc()).limit(limit)
        
        if status:
            query = query.where(ProjectRequirementTask.status == status)
            
        result = await session.execute(query)
        tasks = result.scalars().all()
        
        return TaskListResponse(
            success=True,
            count=len(tasks),
            tasks=[
                TaskListItem(
                    id=t.id,
                    title=t.task_data.get("title", ""),
                    status=t.status,
                    progress=t.progress,
                    priority=t.task_data.get("priority", "medium"),
                    has_subtasks=len(t.subtasks) > 0 if hasattr(t, 'subtasks') else False,
                    created_at=t.created_at.isoformat() if t.created_at else None
                )
                for t in tasks
            ]
        )