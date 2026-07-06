"""
Project Tasks API Routes.
Handles CRUD for Project Tasks (Tickets/Requirements).
"""

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.api.deps import TokenDep, TokenDepOptional
from app.api.schemas.tasks import (
    TaskCreateRequest,
    TaskExecutionResponse,
    TaskStatusUpdate,
    TaskUpdateRequest,
)
from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.evocloud import evocloud_manager
from app.utils.template import render_template

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])

# --- Helper ---
def get_token(authorization: str | None = Header(None)):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return authorization

@router.get("/")
async def get_project_tasks(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    status: int | None = None,
    token: TokenDepOptional = None,
):
    """
    Get a list of tasks for a specific project.
    """
    res = await evocloud_manager.api.get_project_tasks(
        project_id=project_id,
        page=page,
        page_size=page_size,
        status=status,
    )
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to get tasks")
        )

    return res.get("data", {})

@router.get("/{task_id}")
async def get_task_detail(task_id: int, token: TokenDep):
    """
    Get details of a specific task.
    """
    res = await evocloud_manager.api.get_task_detail(task_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to get task detail")
        )

    return res.get("data", {})

@router.post("/")
async def create_task(req: TaskCreateRequest, authorization: str | None = Header(None)):
    """
    Create a new task.
    """
    token = get_token(authorization)
    # Convert Pydantic model to dict, exclude None to let backend handle defaults
    data = req.model_dump(exclude_none=True)

    res = await evocloud_manager.api.create_task(data)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to create task")
        )

    return res

@router.put("/{task_id}")
async def update_task(task_id: int, req: TaskUpdateRequest, authorization: str | None = Header(None)):
    """
    Update a task.
    """
    token = get_token(authorization)
    data = req.model_dump(exclude_none=True)
    data["task_id"] = task_id  # Ensure ID is passed if needed by backend, though URL param usually sufficient for routing

    res = await evocloud_manager.api.update_task(task_id, data)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to update task")
        )

    return res

@router.delete("/{task_id}")
async def delete_task(task_id: int, authorization: str | None = Header(None)):
    """
    Delete a task.
    """
    token = get_token(authorization)
    res = await evocloud_manager.api.delete_task(task_id)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to delete task")
        )

    return res

@router.put("/{task_id}/status")
async def update_task_status_endpoint(task_id: int, req: TaskStatusUpdate, authorization: str | None = Header(None)):
    """
    Update task status and progress.
    """
    token = get_token(authorization)
    res = await evocloud_manager.api.update_task_status(task_id, req.status, req.progress or 0)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to update task status")
        )

    return res

@router.post("/{task_id}/execute")
async def execute_task(task_id: int, bg_tasks: BackgroundTasks, authorization: str | None = Header(None)):
    """
    Trigger Autonomous Agent to execute the task.
    """
    token = get_token(authorization)

    # 1. Fetch Task Detail
    task_res = await evocloud_manager.api.get_task_detail(task_id)
    if task_res.get("code") != 0:
        raise HTTPException(status_code=400, detail="Failed to fetch task details")

    task = task_res.get("data", {})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Construct Prompt
    # Format the task information into a clear instruction for the agent
    prompt = render_template(
        "core/engine/tasks/execution_instruction.prompt.j2",
        title=task.get("task_title"),
        desc=task.get("task_desc"),
        key_modules=task.get("key_modules_list", []),
        tech_challenges=task.get("technical_challenges_list", []),
        deliverables=task.get("deliverables_list", []),
        complexity=task.get("implementation_complexity", "Unknown"),
    )

    # 3. Generate Thread ID
    # Use task ID in thread ID to allow resuming/tracking specific to this task
    thread_id = f"task-{task_id}-{int(time.time())}"

    # 4. Trigger Unified Dispatcher
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=prompt,
        project_id=task.get("project_id", DEFAULT_PROJECT_ID),
        metadata={"task_id": task_id, "goal_prefix": "[Task Execution] "},
    )

    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    return TaskExecutionResponse(
        status="queued",
        thread_id=thread_id,
        message="Agent execution started (Local BG)",
    )
