"""User-side endpoints for the task queue (proposal confirmation + acceptance).

Agent-facing `tasks` tool intentionally lacks these actions (execution-power
isolation): proposed -> pending and acceptance verdicts are user decisions,
performed via this API (TaskQueueService enforces the status machine).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.api.schemas.tasks_queue import (
    TaskCreateRequest,
    TaskEditRequest,
    WorkflowCreateRequest,
    WorkflowEditRequest,
)
from app.core.config import settings
from app.domain.tasks.schemas import WorkflowStageSpec
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
    task_workflow_round,
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
            select(Repository.member_id).where(Repository.project_id == project_id)
        )
        owner_id = result.scalar_one_or_none()
    if owner_id != _member_id(user):
        raise HTTPException(status_code=404, detail="project not found")


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
            skills=body.skills,
            acceptance_criteria=body.acceptance_criteria,
        )
    except TaskQueueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "success": True,
        "id": task.id,
        "parent_id": task.parent_id,
        "status": task.status,
    }


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
            skills=body.skills,
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
    # workflow 聚合刷新已内嵌 submit_acceptance（advance/acceptance 单点，
    # 路由层不再二次 refresh——2026-09-25 冗余清理）
    return {"success": True, "id": task.id, "status": task.status}


@router.post("/queue/{task_id}/reject")
async def reject_task(
    task_id: str, current_user: CurrentUser, body: dict[str, Any] | None = None
) -> dict[str, Any]:
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
    # workflow 聚合刷新已内嵌 submit_acceptance（advance/acceptance 单点，
    # 路由层不再二次 refresh——2026-09-25 冗余清理）
    return {"success": True, "id": task.id, "status": task.status}


@router.get("/queue/dashboard")
async def queue_dashboard(
    current_user: CurrentUser, project_id: int | None = None
) -> dict[str, Any]:
    """Aggregated KPIs for the autonomous duty dashboard (counts + tokens + state)."""
    if project_id is not None:
        await _ensure_project_access(project_id, current_user)
    member_id = (
        _member_id(current_user)
        if settings.MULTI_TENANT_MODE and project_id is None
        else None
    )
    return (
        await TaskQueueService.dashboard(project_id, member_id=member_id)
    ).model_dump()


@router.get("/queue/hitl-pending")
async def hitl_pending_tasks(current_user: CurrentUser) -> dict[str, Any]:
    """Pending HITL requests bound to duty task threads (agent_*/wakeup_*/duty_*).

    Surfaces approvals the operator must make while away — the workbench
    aggregates them here; the chat page owns the interactive approval card.
    Multi-tenant: fail-closed — only requests whose task resolves to the
    caller are returned (unattributable requests are dropped, not exposed).
    查询/归属逻辑在 TaskQueueService.pending_hitl_requests（与 dashboard
    awaiting_human 共用 pending_requests_by_threads，2026-09-25 收敛）。
    """
    member_scope = _member_id(current_user) if settings.MULTI_TENANT_MODE else None
    items = await TaskQueueService.pending_hitl_requests(member_scope)
    return {"success": True, "count": len(items), "items": items}


@router.get("/queue")
async def list_queue(
    current_user: CurrentUser,
    status: str | None = None,
    project_id: int | None = None,
    root_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    order: Literal["queue", "recent"] = "recent",
) -> dict[str, Any]:
    """Queue listing for the task board (stage 4 UI reads the same data).

    分页：``limit``（≤200）+ ``offset``；多取 1 行探测 ``has_more``——
    此前超 50 条静默消失（审计 9.4）。

    ``order``：
    - ``recent``：看板序（updated_at desc），任务一有更新就冒顶；
    - ``queue``：派发序（priority → due → category），与 supervisor 同款，
      适合值守工作台这种需要稳定执行视图的界面。
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
        order=order,
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

            result = await session.execute(
                select(TaskArtifact)
                .where(TaskArtifact.task_id.in_(task_ids))
                .order_by(TaskArtifact.created_at.asc())
            )
            for artifact in result.scalars():
                artifacts_by_task.setdefault(artifact.task_id, []).append(artifact)

            if thread_ids:
                result = await session.execute(
                    select(AgentActivity).where(AgentActivity.thread_id.in_(thread_ids))
                )
                for activity in result.scalars():
                    metrics_by_thread[str(activity.thread_id)] = activity

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
    # 阶段任务的流水线归属名（wf: 任务在画布/节点页要能回溯所属流水线；
    # TaskWorkflow 是独立表，容器实体此前对前端不可见）
    wf_ids = {tid for t in rows if (tid := task_workflow_id(t))}
    wf_names: dict[str, str] = {}
    if wf_ids:
        async with session_scope() as session:
            wf_rows = (
                await session.execute(
                    select(TaskWorkflow.id, TaskWorkflow.title).where(
                        TaskWorkflow.id.in_(wf_ids)
                    )
                )
            ).all()
            wf_names = dict(wf_rows)

    return {
        "success": True,
        "count": len(rows),
        "has_more": has_more,
        "next_offset": offset + len(rows) if has_more else None,
        "items": [
            {
                "project_id": t.project_id,
                "parent_id": t.parent_id,
                "workflow_name": wf_names.get(str(task_workflow_id(t) or "")),
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
                "acceptance_criteria": getattr(t, "acceptance_criteria", None),
                "review_count": t.review_count,
                "workflow_round": task_workflow_round(t),
                "review_pending": task_review_pending(t),
                "escalated": bool((t.acceptance or {}).get("escalated")),
                "origin_thread_id": t.origin_thread_id,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "next_run_at": (t.next_run_at.isoformat() if t.next_run_at else None),
                "last_thread_id": t.last_thread_id,
                "runs": runs_by_task.get(t.id, []),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
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


@router.post("/workflows")
async def create_workflow_any(
    body: WorkflowCreateRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """通用周期工作流提案（编排/触发住 workflow，轮次实例化阶段任务）。

    与 /workflows/growth（硬编码五阶段商城流水线）并列的通用入口：
    Agent/用户建"周期流水线"必须走这里，而不是 recurring 根任务 + 依赖子树
    （该组合没有编排语义，是 2026-09-25 #T-1 事故的根因）。
    """
    await _ensure_project_access(body.project_id, current_user)
    try:
        workflow = await WorkflowService.create_workflow(
            project_id=body.project_id,
            member_id=_member_id(current_user),
            title=body.title,
            goal=body.goal,
            trigger_spec=body.trigger_spec,
            origin_thread_id=body.origin_thread_id,
            stages=[
                WorkflowStageSpec(
                    key=s.key,
                    title=s.title,
                    description=s.description,
                    category=s.category,
                    priority=s.priority.value,
                    risk_level=s.risk_level.value if s.risk_level else None,
                    deps=s.deps,
                )
                for s in body.stages
            ],
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "workflow": _workflow_summary_payload(workflow)}


@router.post("/workflows/{workflow_id}/confirm")
async def confirm_workflow(
    workflow_id: str, current_user: CurrentUser
) -> dict[str, Any]:
    """用户确认编排提案：proposed → armed（触发器上膛）。"""
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
        await _ensure_project_access(workflow.project_id, current_user)
        armed = await WorkflowService.confirm_workflow(workflow_id)
    except WorkflowError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"success": True, "id": armed.id, "status": armed.status}


@router.put("/workflows/{workflow_id}")
async def edit_workflow(
    workflow_id: str, body: WorkflowEditRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """取消工作流（切断触发器 + 终态化在飞阶段任务）。"""
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
        await _ensure_project_access(workflow.project_id, current_user)
        if body.cancel:
            cancelled = await WorkflowService.cancel_workflow(workflow_id)
            return {"success": True, "id": cancelled.id, "status": cancelled.status}
        if body.trigger_spec is not None:
            raise HTTPException(
                status_code=422,
                detail="trigger_spec edit not supported yet; cancel and recreate",
            )
        raise HTTPException(status_code=422, detail="nothing to update")
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    project_id: int | None = None, current_user: CurrentUser = None
) -> dict[str, Any]:
    """List recent workflows so history survives browser sessions.

    ``project_id`` 可选：全局视图（工作空间）不传时返回全量最近工作流
    （提案 tab 需要在全局 scope 下也能看到工作流提案；多租户下按归属过滤）。
    """
    if project_id is not None:
        await _ensure_project_access(project_id, current_user)
    member_id = (
        _member_id(current_user)
        if settings.MULTI_TENANT_MODE and project_id is None
        else None
    )
    workflows = await WorkflowService.list_workflows(project_id, member_id=member_id)
    return {
        "success": True,
        "count": len(workflows),
        "items": [_workflow_summary_payload(workflow) for workflow in workflows],
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, current_user: CurrentUser) -> dict[str, Any]:
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _ensure_project_access(workflow.project_id, current_user)
    tasks = await WorkflowService.list_tasks(
        workflow_id, project_id=workflow.project_id
    )
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


def _workflow_payload(
    workflow: TaskWorkflow, tasks: list[ProjectTask]
) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "title": workflow.title,
        "goal": workflow.goal,
        "type": workflow.workflow_type,
        "status": workflow.status,
        "inputs": workflow.inputs,
        "trigger_spec": workflow.trigger_spec,
        "next_run_at": workflow.next_run_at.isoformat()
        if workflow.next_run_at
        else None,
        "round_no": workflow.round_no,
        "tasks": [
            {
                "id": task.id,
                # 阶段 key 在 source_ref（通用轮次路径）；task_data.workflow_stage
                # 仅为 growth 存量行的只读兜底
                "stage": (task.source_ref or {}).get("stage")
                or (task.task_data or {}).get("workflow_stage"),
                "round": (task.source_ref or {}).get("round"),
                "status": task.status,
                "risk_level": task.risk_level,
                "dependencies": task_dependencies(task),
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
        "trigger_spec": workflow.trigger_spec,
        "next_run_at": workflow.next_run_at.isoformat()
        if workflow.next_run_at
        else None,
        "round_no": workflow.round_no,
        # 阶段模板（提案卡渲染 DAG 链用；growth 流水线无模板则空）
        "stages": [
            {
                "key": s.get("key"),
                "title": s.get("title"),
                "deps": s.get("deps") or [],
            }
            for s in (workflow.inputs or {}).get("stage_template") or []
        ],
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
