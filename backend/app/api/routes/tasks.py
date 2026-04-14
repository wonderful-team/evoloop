"""
Project Tasks API Routes.
Handles CRUD for Project Tasks (Tickets/Requirements).
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.api.deps import TokenDep, TokenDepOptional
from app.api.responses import BaseAPIResponse
from app.core.evocloud import evocloud_manager
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


# --- Helper ---
def get_token(authorization: str | None = Header(None)):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return authorization


class TaskCreateRequest(ScopedRequest):
    project_id: int
    task_title: str
    task_desc: str | None = ""
    # Optional fields that match the AI Enhanced structure
    priority: int = 2
    match_score: float | None = None
    relevance_analysis: str | None = None
    key_modules: Any | None = None  # List or Str
    technical_challenges: Any | None = None
    implementation_complexity: str | None = None
    deliverables: Any | None = None


class TaskUpdateRequest(DynamicBaseModel):
    task_title: str | None = None
    task_desc: str | None = None
    priority: int | None = None
    status: int | None = None
    progress: int | None = None
    # AI fields are also updateable
    match_score: float | None = None
    relevance_analysis: str | None = None
    key_modules: Any | None = None
    technical_challenges: Any | None = None
    implementation_complexity: str | None = None
    deliverables: Any | None = None


class TaskStatusUpdate(DynamicBaseModel):
    status: int
    progress: int | None = 0


class TaskExecutionResponse(BaseAPIResponse):
    status: str
    thread_id: str


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
    res = await evocloud_manager.api.get_task_detail(task_id)
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
    from app.i18n.service import i18n

    prompt = i18n.get(
        "tasks.execution_instruction",
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

    # 4. Trigger Local Background Task
    from app.core.engine.background_agent import run_agent_background

    # Construct Inputs (Serialized)
    # prompt is string.
    messages = [{"type": "human", "content": prompt}]

    inputs = {
        "messages": messages,
        "project_id": task.get("project_id", 1),
        "task_title": task.get("task_title"),
    }

    # --- PERSIST AUTOMATED USER MESSAGE ---
    # We must manually save the prompt as a user message so it appears in history.
    from datetime import datetime, timezone

    from app.infrastructure.database.sql.database import session_scope
    from app.models import Conversation, Message

    try:
        async with session_scope() as session:
            # Upsert Conversation
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                conversation = Conversation(
                    id=thread_id,
                    project_id=task.get("project_id", 1),
                    title=task.get("task_title"),
                )
                session.add(conversation)
            else:
                conversation.updated_at = datetime.now(timezone.utc)

            # Log User Message (The constructed prompt)
            user_msg = Message(
                thread_id=thread_id,
                project_id=task.get("project_id", 1),
                role="human",
                content=prompt,
                thinking=None,
            )
            session.add(user_msg)
            await session.flush()  # Ensure it lands
            logger.info(f"Persisted task trigger message for thread {thread_id}")
    except Exception as e:
        logger.error(f"Failed to persist task message {thread_id}: {e}")
    # --------------------------------------

    bg_tasks.add_task(run_agent_background, thread_id, inputs)

    return TaskExecutionResponse(
        status="queued",
        thread_id=thread_id,
        message="Agent execution started (Local BG)",
    )
