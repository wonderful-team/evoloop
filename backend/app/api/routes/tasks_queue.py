"""User-side endpoints for the task queue (proposal confirmation + acceptance).

Agent-facing `tasks` tool intentionally lacks these actions (execution-power
isolation): proposed -> pending and acceptance verdicts are user decisions,
performed via this API (TaskQueueService enforces the status machine).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.core.config import settings
from app.domain.tasks.service import TaskQueueError, TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.codebase import Repository
from app.models.project import ProjectTask

router = APIRouter(tags=["tasks-queue"])


def _member_id(user: User) -> int:
    return int(user.id)


async def _ensure_task_access(task: ProjectTask, user: User) -> None:
    if not settings.MULTI_TENANT_MODE:
        return
    owner_id = task.member_id or await TaskQueueService.resolve_member_id(task)
    if owner_id != _member_id(user):
        raise HTTPException(status_code=404, detail="task not found")


async def _ensure_project_access(project_id: int, user: User) -> None:
    if not settings.MULTI_TENANT_MODE or project_id == 0:
        return
    async with session_scope() as session:
        result = await session.execute(
            select(Repository.member_id).where(
                Repository.project_id == project_id
            )
        )
        owner_id = result.scalar_one_or_none()
    if owner_id != _member_id(user):
        raise HTTPException(status_code=404, detail="project not found")


@router.post("/queue")
async def create_task(body: dict[str, Any], current_user: CurrentUser) -> dict[str, Any]:
    """User creates a task (board form: title/description/type/priority...)."""
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    project_id = int(body.get("project_id") or 0)
    await _ensure_project_access(project_id, current_user)
    task = await TaskQueueService.create_task(
        project_id=project_id,
        title=title,
        description=str(body.get("description") or ""),
        type=str(body.get("type") or "once"),
        source="user",
        category=body.get("category"),
        priority=str(body.get("priority") or "medium"),
        risk_level=body.get("risk_level"),
        trigger_spec=body.get("trigger_spec"),
        member_id=_member_id(current_user),
    )
    return {"success": True, "id": task.id, "status": task.status}


@router.put("/queue/{task_id}")
async def edit_task(task_id: str, body: dict[str, Any], current_user: CurrentUser) -> dict[str, Any]:
    """User edits task fields (title/description/priority/risk/type/trigger)."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    try:
        fresh = await TaskQueueService.edit_task(
            task_id,
            title=str(body["title"]) if body.get("title") is not None else None,
            description=(
                str(body["description"]) if body.get("description") is not None else None
            ),
            priority=str(body["priority"]) if body.get("priority") is not None else None,
            risk_level=body.get("risk_level"),
            task_type=str(body["type"]) if body.get("type") is not None else None,
            trigger_spec=(
                str(body["trigger_spec"]) if body.get("trigger_spec") is not None else None
            ),
            cancel=body.get("status") == "cancelled",
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"success": True, "id": fresh.id, "status": fresh.status}


@router.post("/queue/{task_id}/confirm")
async def confirm_proposal(task_id: str, current_user: CurrentUser) -> dict[str, Any]:
    """User confirms an Agent proposal: proposed -> pending."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    try:
        task = await TaskQueueService.advance_task(task_id, "pending")
    except TaskQueueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "id": task.id, "status": task.status}


@router.post("/queue/{task_id}/accept")
async def accept_task(task_id: str, current_user: CurrentUser) -> dict[str, Any]:
    """User accepts a task under waiting_acceptance: -> completed."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    try:
        task = await TaskQueueService.submit_acceptance(
            task_id, by="user", verdict="accepted"
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "id": task.id, "status": task.status}


@router.post("/queue/{task_id}/reject")
async def reject_task(task_id: str, current_user: CurrentUser, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """User rejects: -> in_progress (rework loop) with mandatory feedback."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    feedback = str((body or {}).get("feedback") or "").strip()
    if not feedback:
        raise HTTPException(status_code=422, detail="feedback is required")
    try:
        task = await TaskQueueService.submit_acceptance(
            task_id, by="user", verdict="rejected", feedback=feedback
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "id": task.id, "status": task.status}


@router.get("/queue/dashboard")
async def queue_dashboard(current_user: CurrentUser, project_id: int | None = None) -> dict[str, Any]:
    """Aggregated KPIs for the autonomous duty dashboard (counts + tokens + state)."""
    if project_id is not None:
        await _ensure_project_access(project_id, current_user)
    return (await TaskQueueService.dashboard(project_id)).model_dump()


@router.get("/queue")
async def list_queue(current_user: CurrentUser, status: str | None = None, project_id: int | None = None) -> dict[str, Any]:
    """Queue listing for the task board (stage 4 UI reads the same data)."""
    rows = await TaskQueueService.list_tasks(
        status=status, project_id=project_id, limit=50
    )
    if settings.MULTI_TENANT_MODE:
        rows = [
            task
            for task in rows
            if task.member_id == _member_id(current_user)
            or await TaskQueueService.resolve_member_id(task)
            == _member_id(current_user)
        ]
    return {
        "success": True,
        "count": len(rows),
        "items": [
            {
                "id": t.id,
                "title": (t.task_data or {}).get("title"),
                "description": t.description,
                "type": t.type,
                "status": t.status,
                "category": (t.task_data or {}).get("category"),
                "priority": (t.task_data or {}).get("priority"),
                "risk_level": t.risk_level,
                "source": t.source,
                "provenance": t.source_ref,
                "self_check": t.self_check,
                "acceptance": t.acceptance,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "next_run_at": (
                    t.next_run_at.isoformat() if t.next_run_at else None
                ),
                "last_thread_id": t.last_thread_id,
            }
            for t in rows
        ],
    }
