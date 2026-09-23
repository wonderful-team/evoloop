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
from app.api.schemas.tasks_queue import TaskCreateRequest, TaskEditRequest
from app.core.config import settings
from app.domain.tasks.service import (
    TaskQueueError,
    TaskQueueService,
    task_category,
    task_dependencies,
    task_last_error,
    task_priority,
    task_review_pending,
    task_title,
    task_version,
    task_workflow_id,
    task_workflow_retry_count,
)
from app.domain.tasks.workflows import WorkflowError, WorkflowService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.codebase import Repository
from app.models.conversation import AgentActivity, Message
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
    workflow_id = task_workflow_id(task)
    if workflow_id:
        await WorkflowService.refresh_status(str(workflow_id))


@router.post("/queue")
async def create_task(
    body: TaskCreateRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """User creates a task (board form: title/description/type/priority...)."""
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required")
    project_id = body.project_id
    await _ensure_project_access(project_id, current_user)
    try:
        task = await TaskQueueService.create_task(
            project_id=project_id,
            title=body.title,
            description=body.description or "",
            type=body.type.value,
            source="user",
            category=body.category,
            priority=body.priority.value,
            risk_level=body.risk_level.value if body.risk_level else None,
            due_at=body.due_at,
            trigger_spec=body.trigger_spec,
            member_id=_member_id(current_user),
            parent_id=body.parent_id,
            dependencies=body.dependencies,
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"success": True, "id": task.id, "parent_id": task.parent_id, "status": task.status}


@router.get("/queue/{task_id}/artifacts")
async def list_task_artifacts(
    task_id: str, current_user: CurrentUser
) -> dict[str, Any]:
    """Structured artifacts produced by this task (task_artifacts table)."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
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
async def rerun_failed_task(task_id: str, current_user: CurrentUser) -> dict[str, Any]:
    """Re-queue a failed task: failed → pending, clear retry bookkeeping.

    Unblocks a dependent workflow chain (children stay pending until this
    re-runs to completion). Only failed tasks may be re-run.
    """
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    if task.status != "failed":
        raise HTTPException(
            status_code=409, detail=f"task is {task.status}, not failed"
        )
    from sqlalchemy import update as sa_update

    async with session_scope() as session:
        result_update = await session.execute(
            sa_update(ProjectTask)
            .where(
                ProjectTask.id == task_id,
                ProjectTask.status == "failed",
                ProjectTask.version == task_version(task),
            )
            .values(last_error=None, last_result=None, version=task_version(task) + 1)
        )
        if result_update.rowcount == 0:
            raise HTTPException(status_code=409, detail="task version conflict")
    updated = await TaskQueueService.advance_task(task_id, "pending")
    return {"success": True, "id": updated.id, "status": updated.status}


@router.put("/queue/{task_id}")
async def edit_task(
    task_id: str, body: TaskEditRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """User edits task fields (title/description/priority/risk/type/trigger)."""
    task = await TaskQueueService.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await _ensure_task_access(task, current_user)
    try:
        fresh = await TaskQueueService.edit_task(
            task_id,
            title=body.title,
            description=body.description,
            priority=body.priority.value if body.priority else None,
            risk_level=body.risk_level.value if body.risk_level else None,
            task_type=body.type.value if body.type else None,
            due_at=body.due_at,
            clear_due_at=body.clear_due_at,
            trigger_spec=body.trigger_spec,
            clear_trigger_spec=body.clear_trigger_spec,
            dependencies=body.dependencies,
            cancel=body.cancel or body.status == "cancelled",
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
        task = await TaskQueueService.advance_task(task_id, "pending", by="user")
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
    member_id = (
        _member_id(current_user) if settings.MULTI_TENANT_MODE and project_id is None else None
    )
    return (await TaskQueueService.dashboard(project_id, member_id=member_id)).model_dump()


@router.get("/queue/hitl-pending")
async def hitl_pending_tasks(current_user: CurrentUser) -> dict[str, Any]:
    """Pending HITL requests bound to duty task threads (agent_*/wakeup_*/duty_*).

    Surfaces approvals the operator must make while away — the workbench
    aggregates them here; the chat page owns the interactive approval card.
    Multi-tenant: fail-closed — only requests whose task resolves to the
    caller are returned (unattributable requests are dropped, not exposed).
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
        # 评审 run（origin thread）的审批也聚合：执行者的审批卡在看板，
        # 评审者挂在原对话的审批同样要看板可见（否则评审中被审批链卡死
        # 而用户毫无感知——实测缺口）
        origin_map: dict[str, ProjectTask] = {}
        review_pending = (
            (
                await session.execute(
                    select(ProjectTask).where(
                        ProjectTask.status == "waiting_acceptance",
                        ProjectTask.origin_thread_id.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for t in review_pending:
            if task_review_pending(t):
                origin_map[str(t.origin_thread_id)] = t

        items = []
        member_scope = _member_id(current_user) if settings.MULTI_TENANT_MODE else None
        for r in rows:
            is_origin_thread = str(r.thread_id) in origin_map
            if not str(r.thread_id).startswith(prefixes) and not is_origin_thread:
                continue
            task = None
            if is_origin_thread:
                task = origin_map[str(r.thread_id)]
            else:
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
            if member_scope is not None:
                if task is None:
                    continue  # fail-closed：无法归属的请求不暴露
                owner = task.member_id or await TaskQueueService.resolve_member_id(task)
                if owner != member_scope:
                    continue
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
                     "task_title": task_title(task) if task else None,
                    "task_no": task.task_no if task else None,
                }
            )
        return {"success": True, "count": len(items), "items": items}


@router.get("/queue")
async def list_queue(
    current_user: CurrentUser,
    status: str | None = None,
    project_id: int | None = None,
    root_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Queue listing for the task board (stage 4 UI reads the same data).

    分页：``limit``（≤200）+ ``offset``；多取 1 行探测 ``has_more``——
    此前超 50 条静默消失（审计 9.4）。
    """
    if project_id is not None:
        await _ensure_project_access(project_id, current_user)
    member_id = (
        _member_id(current_user)
        if settings.MULTI_TENANT_MODE and project_id is None
        else None
    )
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = await TaskQueueService.list_tasks(
        status=status,
        project_id=project_id,
        root_only=root_only,
        limit=limit + 1,
        offset=offset,
        member_id=member_id,
        order="recent",
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    task_ids = [task.id for task in rows]
    thread_ids = [task.last_thread_id for task in rows if task.last_thread_id]
    artifacts_by_task: dict[str, list[TaskArtifact]] = {}
    metrics_by_thread: dict[str, AgentActivity] = {}
    elapsed_by_thread: dict[str, int] = {}
    subtasks_counts: dict[str, dict[str, int]] = {}
    runs_by_task: dict[str, list[dict[str, Any]]] = {}
    if task_ids:
        subtasks_counts = await TaskQueueService.get_subtasks_counts(task_ids)
        # attempt 历史（task_runs 过程记录层）：每任务最近 5 次尝试
        from app.models.task_run import TaskRun

        async with session_scope() as session:
            run_rows = (
                await session.execute(
                    select(TaskRun)
                    .where(TaskRun.task_id.in_(task_ids))
                    .order_by(TaskRun.attempt.desc())
                )
            ).scalars().all()
        for run in run_rows:
            runs_by_task.setdefault(run.task_id, []).append(
                {
                    "id": run.id,
                    "thread_id": run.thread_id,
                    "attempt": run.attempt,
                    "status": run.status,
                    "started_at": run.started_at.isoformat()
                    if run.started_at
                    else None,
                    "finished_at": run.finished_at.isoformat()
                    if run.finished_at
                    else None,
                    "error_code": run.error_code,
                    "error_message": run.error_message,
                    "result_summary": run.result_summary,
                }
            )
        for task_id in runs_by_task:
            runs_by_task[task_id] = runs_by_task[task_id][:5]
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
    return {
        "success": True,
        "count": len(rows),
        "has_more": has_more,
        "next_offset": offset + len(rows) if has_more else None,
        "items": [
            {
                "project_id": t.project_id,
                "parent_id": t.parent_id,
                "subtasks_count": subtasks_counts.get(t.id, {}).get("total", 0),
                "subtasks_completed": subtasks_counts.get(t.id, {}).get("completed", 0),
                "elapsed_sec": elapsed_by_thread.get(t.last_thread_id),
                 "workflow_id": task_workflow_id(t),
                 "dependencies": task_dependencies(t),
                "id": t.id,
                "task_no": t.task_no,
                 "title": task_title(t),
                "description": t.description,
                "type": t.type,
                "status": t.status,
                 "category": task_category(t),
                 "priority": task_priority(t),
                "risk_level": t.risk_level,
                "source": t.source,
                "provenance": t.source_ref,
                "self_check": t.self_check,
                "acceptance": t.acceptance,
                "review_count": t.review_count,
                 "review_pending": task_review_pending(t),
                "escalated": bool((t.acceptance or {}).get("escalated")),
                "origin_thread_id": t.origin_thread_id,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "next_run_at": (
                    t.next_run_at.isoformat() if t.next_run_at else None
                ),
                "last_thread_id": t.last_thread_id,
                "runs": runs_by_task.get(t.id, []),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
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
                "dependencies": task_dependencies(task),
                "allowed_packages": (task.task_data or {}).get("allowed_packages") or [],
                "last_error": task_last_error(task),
                "retry_count": task_workflow_retry_count(task),
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
