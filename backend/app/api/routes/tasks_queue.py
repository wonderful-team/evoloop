"""User-side endpoints for the task queue (proposal confirmation + acceptance).

Agent-facing `tasks` tool intentionally lacks these actions (execution-power
isolation): proposed -> pending and acceptance verdicts are user decisions,
performed via this API (TaskQueueService enforces the status machine).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.domain.tasks.service import TaskQueueError, TaskQueueService

router = APIRouter(tags=["tasks-queue"])


@router.post("/queue")
async def create_task(body: dict[str, Any]) -> dict[str, Any]:
    """User creates a task (board form: title/description/type/priority...)."""
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    task = await TaskQueueService.create_task(
        project_id=int(body.get("project_id") or 0),
        title=title,
        description=str(body.get("description") or ""),
        type=str(body.get("type") or "once"),
        source="user",
        category=body.get("category"),
        priority=str(body.get("priority") or "medium"),
        risk_level=body.get("risk_level"),
        trigger_spec=body.get("trigger_spec"),
    )
    return {"success": True, "id": task.id, "status": task.status}


@router.put("/queue/{task_id}")
async def edit_task(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """User edits task fields (title/description/priority/risk/type/trigger)."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
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
async def confirm_proposal(task_id: str) -> dict[str, Any]:
    """User confirms an Agent proposal: proposed -> pending."""
    try:
        task = await TaskQueueService.advance_task(task_id, "pending")
    except TaskQueueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "id": task.id, "status": task.status}


@router.post("/queue/{task_id}/accept")
async def accept_task(task_id: str) -> dict[str, Any]:
    """User accepts a task under waiting_acceptance: -> completed."""
    try:
        task = await TaskQueueService.submit_acceptance(
            task_id, by="user", verdict="accepted"
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "id": task.id, "status": task.status}


@router.post("/queue/{task_id}/reject")
async def reject_task(
    task_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """User rejects: -> in_progress (rework loop) with mandatory feedback."""
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
async def queue_dashboard(project_id: int | None = None) -> dict[str, Any]:
    """Aggregated KPIs for the autonomous duty dashboard (counts + tokens + state)."""
    return (await TaskQueueService.dashboard(project_id)).model_dump()


@router.get("/queue")
async def list_queue(
    status: str | None = None, project_id: int | None = None
) -> dict[str, Any]:
    """Queue listing for the task board (stage 4 UI reads the same data)."""
    rows = await TaskQueueService.list_tasks(
        status=status, project_id=project_id, limit=50
    )
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
