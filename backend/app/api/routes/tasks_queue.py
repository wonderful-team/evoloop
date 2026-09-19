"""User-side endpoints for the task queue (proposal confirmation + acceptance).

Agent-facing `tasks` tool intentionally lacks these actions (execution-power
isolation): proposed -> pending and acceptance verdicts are user decisions,
performed via this API (TaskQueueService enforces the status machine).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.core.config import settings
from app.domain.tasks.service import TaskQueueError, TaskQueueService
from app.domain.tasks.workflows import WorkflowError, WorkflowService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.conversation import Message
from app.models.codebase import Repository
from app.models.conversation import AgentActivity
from app.models.project import ProjectTask
from app.models.task_workflow import TaskArtifact, TaskWorkflow

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


async def _refresh_task_workflow(task: ProjectTask) -> None:
    """Recompute workflow status after a user-side task transition."""
    workflow_id = (task.task_data or {}).get("workflow_id")
    if workflow_id:
        await WorkflowService.refresh_status(str(workflow_id))


@router.post("/queue")
async def create_task(body: dict[str, Any], current_user: CurrentUser) -> dict[str, Any]:
    """User creates a task (board form: title/description/type/priority...)."""
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    project_id = int(body.get("project_id") or 0)
    await _ensure_project_access(project_id, current_user)
    try:
        due_at = (
            datetime.fromisoformat(str(body["due_at"]))
            if body.get("due_at") is not None
            else None
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid due_at") from e
    task = await TaskQueueService.create_task(
        project_id=project_id,
        title=title,
        description=str(body.get("description") or ""),
        type=str(body.get("type") or "once"),
        source="user",
        category=body.get("category"),
        priority=str(body.get("priority") or "medium"),
        risk_level=body.get("risk_level"),
        due_at=due_at,
        trigger_spec=body.get("trigger_spec"),
        member_id=_member_id(current_user),
    )
    return {"success": True, "id": task.id, "status": task.status}


@router.get("/queue/{task_id}/artifacts")
async def list_task_artifacts(task_id: str) -> dict[str, Any]:
    """Structured artifacts produced by this task (task_artifacts table)."""
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(TaskArtifact)
                    .where(TaskArtifact.task_id == task_id)
                    .order_by(TaskArtifact.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "success": True,
            "items": [
                {
                    "id": a.id,
                    "stage": a.stage,
                    "artifact_type": a.artifact_type,
                    "status": a.status,
                    "version": a.version,
                    "summary": a.summary,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in rows
            ],
        }


@router.post("/queue/{task_id}/rerun")
async def rerun_failed_task(task_id: str) -> dict[str, Any]:
    """Re-queue a failed task: failed → pending, clear retry bookkeeping.

    Unblocks a dependent workflow chain (children stay pending until this
    re-runs to completion). Only failed tasks may be re-run.
    """
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != "failed":
        raise HTTPException(
            status_code=409, detail=f"task is {task.status}, not failed"
        )
    td = task.task_data or {}
    td.pop("last_error", None)
    td.pop("last_result", None)
    from sqlalchemy import update as sa_update

    async with session_scope() as session:
        await session.execute(
            sa_update(ProjectTask)
            .where(ProjectTask.id == task_id)
            .values(task_data=td)
        )
    updated = await TaskQueueService.advance_task(task_id, "pending")
    return {"success": True, "id": updated.id, "status": updated.status}


@router.put("/queue/{task_id}")
async def edit_task(task_id: str, body: dict[str, Any], current_user: CurrentUser) -> dict[str, Any]:
    """User edits task fields (title/description/priority/risk/type/trigger)."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    try:
        due_at = (
            datetime.fromisoformat(str(body["due_at"]))
            if body.get("due_at") is not None
            else None
        )
        fresh = await TaskQueueService.edit_task(
            task_id,
            title=str(body["title"]) if body.get("title") is not None else None,
            description=(
                str(body["description"]) if body.get("description") is not None else None
            ),
            priority=str(body["priority"]) if body.get("priority") is not None else None,
            risk_level=body.get("risk_level"),
            task_type=str(body["type"]) if body.get("type") is not None else None,
            due_at=due_at,
            clear_due_at=bool(body.get("clear_due_at")),
            trigger_spec=(
                str(body["trigger_spec"]) if body.get("trigger_spec") is not None else None
            ),
            clear_trigger_spec=bool(body.get("clear_trigger_spec")),
            cancel=body.get("status") == "cancelled",
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid due_at") from e
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
    await _refresh_task_workflow(task)
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
    await _refresh_task_workflow(task)
    return {"success": True, "id": task.id, "status": task.status}


@router.get("/queue/dashboard")
async def queue_dashboard(current_user: CurrentUser, project_id: int | None = None) -> dict[str, Any]:
    """Aggregated KPIs for the autonomous duty dashboard (counts + tokens + state)."""
    if project_id is not None:
        await _ensure_project_access(project_id, current_user)
    return (await TaskQueueService.dashboard(project_id)).model_dump()


@router.get("/queue/hitl-pending")
async def hitl_pending_tasks(current_user: CurrentUser) -> dict[str, Any]:
    """Pending HITL requests bound to duty task threads (agent_*/wakeup_*/duty_*).

    Surfaces approvals the operator must make while away — the workbench
    aggregates them here; the chat page owns the interactive approval card.
    """
    from app.models.conversation import HumanRequest

    prefixes = ("agent_", "wakeup_", "duty_")
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(HumanRequest)
                    .where(HumanRequest.status == "pending")
                    .order_by(HumanRequest.created_at.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        items = []
        for r in rows:
            if not str(r.thread_id).startswith(prefixes):
                continue
            task = (
                (
                    await session.execute(
                        select(ProjectTask).where(
                            ProjectTask.last_thread_id == r.thread_id
                        )
                    )
                )
                .scalars()
                .first()
            )
            items.append(
                {
                    "request_id": r.id,
                    "thread_id": r.thread_id,
                    "type": r.type,
                    "description": r.description,
                    "context": r.context,
                    "options": r.options or [],
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "task_id": task.id if task else None,
                    "task_title": (task.task_data or {}).get("title") if task else None,
                }
            )
        return {"success": True, "count": len(items), "items": items}


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
    task_ids = [task.id for task in rows]
    thread_ids = [task.last_thread_id for task in rows if task.last_thread_id]
    artifacts_by_task: dict[str, list[TaskArtifact]] = {}
    metrics_by_thread: dict[str, AgentActivity] = {}
    elapsed_by_thread: dict[str, int] = {}
    if task_ids:
        async with session_scope() as session:
            result = await session.execute(
                select(TaskArtifact)
                .where(TaskArtifact.task_id.in_(task_ids))
                .order_by(TaskArtifact.created_at.asc())
            )
            for artifact in result.scalars():
                artifacts_by_task.setdefault(artifact.task_id, []).append(artifact)
        if thread_ids:
            result = await session.execute(
                select(AgentActivity).where(
                    AgentActivity.thread_id.in_(thread_ids)
                )
            )
            for activity in result.scalars():
                metrics_by_thread[str(activity.thread_id)] = activity
            # per-thread elapsed = first→last message span
            from sqlalchemy import func

            span_rows = (
                await session.execute(
                    select(
                        Message.thread_id,
                        func.min(Message.created_at).label("mn"),
                        func.max(Message.created_at).label("mx"),
                    )
                    .where(Message.thread_id.in_(thread_ids))
                    .group_by(Message.thread_id)
                )
            ).all()
            for tid, mn, mx in span_rows:
                if mn and mx:
                    elapsed_by_thread[str(tid)] = max(
                        0, int((mx - mn).total_seconds())
                    )
    rows.sort(key=lambda task: task.updated_at or task.created_at, reverse=True)
    return {
        "success": True,
        "count": len(rows),
        "items": [
            {
                "project_id": t.project_id,
                "elapsed_sec": elapsed_by_thread.get(t.last_thread_id),
                "workflow_id": (t.task_data or {}).get("workflow_id"),
                "dependencies": (t.task_data or {}).get("dependencies") or [],
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
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "workflow_id": (t.task_data or {}).get("workflow_id"),
                "workflow_stage": (t.task_data or {}).get("workflow_stage"),
                "run": (
                    {
                        "thread_id": activity.thread_id,
                        "status": activity.status,
                        "llm_calls": int(activity.llm_calls or 0),
                        "input_tokens": int(activity.input_tokens or 0),
                        "output_tokens": int(activity.output_tokens or 0),
                        "tool_errors": int(activity.tool_errors or 0),
                    }
                    if (activity := metrics_by_thread.get(t.last_thread_id or ""))
                    else None
                ),
                "artifacts": [
                    _artifact_payload(artifact)
                    for artifact in artifacts_by_task.get(t.id, [])
                ],
            }
            for t in rows
        ],
    }


@router.post("/workflows/growth")
async def create_growth_workflow(
    body: dict[str, Any], current_user: CurrentUser
) -> dict[str, Any]:
    """Create the text-only commerce growth workflow."""
    project_id = int(body.get("project_id") or 0)
    await _ensure_project_access(project_id, current_user)
    try:
        workflow, tasks = await WorkflowService.create_growth_workflow(
            project_id=project_id,
            member_id=_member_id(current_user),
            title=str(body.get("title") or ""),
            goal=str(body.get("goal") or ""),
            inputs=body.get("inputs") if isinstance(body.get("inputs"), dict) else {},
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "workflow": _workflow_payload(workflow, tasks)}


@router.get("/workflows")
async def list_workflows(
    project_id: int, current_user: CurrentUser
) -> dict[str, Any]:
    """List recent workflows so history survives browser sessions."""
    await _ensure_project_access(project_id, current_user)
    workflows = await WorkflowService.list_workflows(project_id)
    return {
        "success": True,
        "count": len(workflows),
        "items": [_workflow_summary_payload(workflow) for workflow in workflows],
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str, current_user: CurrentUser
) -> dict[str, Any]:
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _ensure_project_access(workflow.project_id, current_user)
    tasks = await WorkflowService.list_tasks(workflow_id, project_id=workflow.project_id)
    return {"success": True, "workflow": _workflow_payload(workflow, tasks)}


@router.get("/workflows/{workflow_id}/artifacts")
async def list_workflow_artifacts(
    workflow_id: str, current_user: CurrentUser
) -> dict[str, Any]:
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _ensure_project_access(workflow.project_id, current_user)
    artifacts = await WorkflowService.list_artifacts(
        workflow_id, project_id=workflow.project_id
    )
    return {
        "success": True,
        "count": len(artifacts),
        "items": [_artifact_payload(artifact) for artifact in artifacts],
    }


def _workflow_payload(workflow: TaskWorkflow, tasks: list[ProjectTask]) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "title": workflow.title,
        "goal": workflow.goal,
        "type": workflow.workflow_type,
        "status": workflow.status,
        "inputs": workflow.inputs,
        "tasks": [
            {
                "id": task.id,
                "stage": (task.task_data or {}).get("workflow_stage"),
                "role": (task.task_data or {}).get("workflow_role"),
                "runtime": (task.task_data or {}).get("workflow_runtime"),
                "status": task.status,
                "risk_level": task.risk_level,
                "dependencies": (task.task_data or {}).get("dependencies") or [],
                "allowed_packages": (task.task_data or {}).get("allowed_packages") or [],
                "last_error": (task.task_data or {}).get("last_error"),
                "retry_count": (task.task_data or {}).get("workflow_retry_count", 0),
            }
            for task in tasks
        ],
    }


def _workflow_summary_payload(workflow: TaskWorkflow) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "title": workflow.title,
        "goal": workflow.goal,
        "type": workflow.workflow_type,
        "status": workflow.status,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


def _artifact_payload(artifact: TaskArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "workflow_id": artifact.workflow_id,
        "task_id": artifact.task_id,
        "stage": artifact.stage,
        "type": artifact.artifact_type,
        "status": artifact.status,
        "version": artifact.version,
        "summary": artifact.summary,
        "data": artifact.data,
        "created_at": artifact.created_at.isoformat(),
    }
