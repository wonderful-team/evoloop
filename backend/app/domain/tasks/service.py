"""Task queue service — autonomous task loop stage 1.

Queue semantics on top of the existing ProjectTask table (SSOT).
System principle: the queue only stores and orders; decomposition
(plans, subtasks, immediate actions) belongs to the Agent at runtime.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import case, func, select, update

from app.domain.tasks.constants import (
    PRIORITY_ORDER,
    QUEUE_TRANSITIONS,
    REQUEUE_LIMIT,
    RESULT_MAX,
)
from app.domain.tasks.events import publish_task_queue_event
from app.domain.tasks.notify import push_hitl_notice, task_label
from app.domain.tasks.runtime.wakeup import notify_duty_wakeup
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask
from app.utils.id import gen_uuid
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.task_run import TaskRun

logger = logging.getLogger(__name__)


VALID_SOURCES = frozenset({"user", "agent", "external"})
VALID_RISK_LEVELS = frozenset({"T1", "T2", "T3", "T4"})
VALID_TASK_TYPES = frozenset({"once", "recurring"})
CATEGORY_MAX_LENGTH = 100


def _legacy_value(
    task: ProjectTask, value: object, key: str, default: object = None
) -> object:
    """Read a promoted field from its column, then from legacy task_data."""
    if value is not None:
        return value
    return (task.task_data or {}).get(key, default)


def task_title(task: ProjectTask) -> str | None:
    return _legacy_value(task, task.title, "title")


def task_priority(task: ProjectTask) -> str:
    return str(_legacy_value(task, task.priority, "priority", "medium") or "medium")


def task_category(task: ProjectTask) -> str | None:
    value = _legacy_value(task, task.category, "category")
    return str(value) if value is not None else None


def task_dependencies(task: ProjectTask) -> list[str]:
    value = _legacy_value(task, task.dependencies, "dependencies", [])
    return [str(item) for item in value] if isinstance(value, list) else []


def task_workflow_id(task: ProjectTask) -> str | None:
    value = _legacy_value(task, task.workflow_id, "workflow_id")
    return str(value) if value is not None else None


def task_dispatch_count(task: ProjectTask) -> int:
    return int(_legacy_value(task, task.dispatch_count, "dispatch_count", 0) or 0)


def task_last_result(task: ProjectTask) -> str | None:
    value = _legacy_value(task, task.last_result, "last_result")
    return str(value) if value is not None else None


def task_last_error(task: ProjectTask) -> str | None:
    value = _legacy_value(task, task.last_error, "last_error")
    return str(value) if value is not None else None


def task_review_pending(task: ProjectTask) -> bool:
    return bool(_legacy_value(task, task.review_pending, "review_pending", False))


def task_workflow_retry_count(task: ProjectTask) -> int:
    return int(
        _legacy_value(task, task.workflow_retry_count, "workflow_retry_count", 0) or 0
    )


def task_number(task: ProjectTask) -> int | None:
    value = task.task_no
    if value is None:
        value = (task.task_data or {}).get("task_no")
    return int(value) if value is not None else None


def task_version(task: ProjectTask) -> int:
    return int(task.version or 1)


def _queue_ordering():
    """SQL ordering shared by queue listings and due-task scans."""
    priority_rank = case(
        (ProjectTask.priority == "urgent", 0),
        (ProjectTask.priority == "high", 1),
        (ProjectTask.priority == "medium", 2),
        (ProjectTask.priority == "low", 3),
        else_=2,
    )
    due_at = func.coalesce(ProjectTask.due_at, ProjectTask.next_run_at, _now())
    return (
        priority_rank.asc(),
        due_at.asc(),
        func.coalesce(ProjectTask.category, "").asc(),
        ProjectTask.created_at.asc(),
        ProjectTask.id.asc(),
    )


def _normalize_category(category: str | None) -> str | None:
    if category is None:
        return None
    normalized = str(category).strip()
    if not normalized:
        raise TaskQueueError("category must not be empty")
    if len(normalized) > CATEGORY_MAX_LENGTH:
        raise TaskQueueError(
            f"category must be at most {CATEGORY_MAX_LENGTH} characters"
        )
    return normalized


def _normalize_priority(priority: str | None) -> str:
    normalized = str(priority or "medium").strip().lower()
    if normalized not in PRIORITY_ORDER:
        allowed = ", ".join(PRIORITY_ORDER)
        raise TaskQueueError(
            f"invalid priority: {priority!r}; expected one of {allowed}"
        )
    return normalized


def _normalize_risk(risk_level: str | None) -> str | None:
    if risk_level is None:
        return None
    normalized = str(risk_level).strip().upper()
    if normalized not in VALID_RISK_LEVELS:
        raise TaskQueueError(
            f"invalid risk_level: {risk_level!r}; expected one of T1, T2, T3, T4"
        )
    return normalized


def _normalize_list(value: list | None, field: str) -> list | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TaskQueueError(f"{field} must be a list")
    return list(value)


class TaskQueueError(Exception):
    pass


class EventSpecError(Exception):
    """外部事件 spec 缺必填字段（payload malformed，非队列状态机错误）。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_result(text: str | None) -> str | None:
    if text is None:
        return None
    return text[:RESULT_MAX]


class TaskQueueService:
    """DB-as-queue operations over ProjectTask. All writes are status-machine guarded."""

    @staticmethod
    async def ingest_event(
        source_system: str, event_id: str, spec: dict[str, Any]
    ) -> tuple[ProjectTask, bool]:
        """外部系统消息 → 任务入队（external 入口的全部队列语义）。

        消息经 channel 层归一化（``notifications/mcp_message`` →
        InboundMessageEvent）后进入此处；本层只做三件事：spec 校验、
        幂等（dedup_key = "{source}:{event_id}"）、以 source=external
        落任务（胖 payload，引擎不解释业务）。
        ``contact`` 为会话类消息的回复路由元数据，随 source_ref 落库。
        """
        from app.domain.tasks.constants import INGESTION_REQUIRED_FIELDS

        for field in INGESTION_REQUIRED_FIELDS:
            if not str(spec.get(field) or "").strip():
                raise EventSpecError(f"spec missing required field: {field}")

        dedup_key = f"{source_system}:{event_id}"
        existing = await TaskQueueService.get_by_dedup_key(dedup_key)
        if existing is not None:
            return existing, False  # 幂等重投

        start_hours = spec.get("start_in_hours")
        due_at = (
            utcnow() + timedelta(hours=float(start_hours))
            if start_hours is not None
            else None
        )

        contact = str(spec.get("contact") or "").strip() or None
        channel = str(spec.get("channel") or "").strip() or None
        source_ref: dict[str, Any] = {
            "kind": "event",
            "source_system": source_system,
            "event_id": event_id,
        }
        if contact:
            source_ref["contact"] = contact
        if channel:
            source_ref["channel"] = channel

        task = await TaskQueueService.create_task(
            project_id=int(spec.get("project_id") or 0),
            title=str(spec["title"]),
            description=str(spec.get("description") or ""),
            source="external",
            source_ref=source_ref,
            category=spec.get("category"),
            priority=str(spec.get("priority") or "medium"),
            risk_level=spec.get("risk_level"),
            due_at=due_at,
            dedup_key=dedup_key,
        )
        return task, True

    @staticmethod
    async def create_task(
        *,
        project_id: int,
        title: str,
        description: str = "",
        type: Literal["once", "recurring"] = "once",
        source: str = "user",
        source_ref: dict[str, Any] | None = None,
        category: str | None = None,
        priority: str = "medium",
        risk_level: str | None = None,
        due_at: datetime | None = None,
        trigger_spec: str | None = None,
        dedup_key: str | None = None,
        member_id: int = 0,
        parent_id: str | None = None,
        dependencies: list[str] | None = None,
        tags: list | None = None,
        acceptance_criteria: list | None = None,
        workflow_id: str | None = None,
        workflow_round: int | None = None,
    ) -> ProjectTask:
        """Insert a task row. Entry semantics:
        - source=user → pending (user-planned, accepted as-is)
        - source=agent → proposed (needs user confirmation; T3/T4 may auto-confirm)
        - source=external → proposed; dedup_key enforced (None duplicate raises ValueError)
        """
        title = str(title or "").strip()
        if not title:
            raise TaskQueueError("title is required")
        source = str(source or "").strip().lower()
        if source not in VALID_SOURCES:
            raise TaskQueueError(f"invalid source: {source}")
        priority = _normalize_priority(priority)
        category = _normalize_category(category)
        risk_level = _normalize_risk(risk_level)
        task_type = str(type or "once").strip().lower()
        if task_type not in VALID_TASK_TYPES:
            raise TaskQueueError(f"invalid task type: {type}")
        trigger = str(trigger_spec).strip() if trigger_spec else None
        if task_type == "recurring" and not trigger:
            raise TaskQueueError("recurring tasks require trigger_spec")
        if trigger:
            task_type = "recurring"
        dependencies = _normalize_list(dependencies, "dependencies")
        dependencies = (
            [str(item) for item in dependencies] if dependencies is not None else []
        )
        # 拆解不变量：parent_id 记血统，dependencies 是画布连线与派发顺序的
        # 唯一权威（前端 deriveDutyEdges/布局只认 dependencies）。带 parent_id
        # 创建的子任务自动补父依赖（幂等：显式传入不重复）。recurring 上游
        # 没有 completed 终态，gating 侧按 lineage-only 豁免（见
        # get_due_pending_tasks 与 dispatcher._deps_satisfied）。
        if parent_id and parent_id not in dependencies:
            dependencies.append(str(parent_id))
        tags = _normalize_list(tags, "tags") or []
        acceptance_criteria = (
            _normalize_list(acceptance_criteria, "acceptance_criteria") or []
        )
        workflow_id = str(workflow_id).strip() if workflow_id else None
        if dedup_key:
            existing = await TaskQueueService.get_by_dedup_key(dedup_key)
            if existing is not None:
                return existing  # idempotent re-delivery (any source)

        status = "pending" if source == "user" else "proposed"
        next_run_at = None
        if trigger:
            from app.infrastructure.scheduler.service import SchedulerService

            next_run_at = SchedulerService.calculate_next_run(trigger, _now())
        # 短编号：项目内递增，对话/评审/反馈用 "#T-<n>" 指代（uuid 太重）
        origin_thread_id = str((source_ref or {}).get("ref") or "") or None

        # 并发收敛（审计 F-09）：(project_id, task_no) 唯一索引下，并发
        # max+1 会抛 IntegrityError——捕获后重算重试（≤3 轮）；dedup_key
        # 唯一冲突 = 并发重复投递，回读已有任务幂等返回（不向上炸异常）。
        from sqlalchemy.exc import IntegrityError

        task: ProjectTask | None = None
        for _attempt in range(3):
            async with session_scope() as session:
                max_no = await session.execute(
                    select(func.coalesce(func.max(ProjectTask.task_no), 0)).where(
                        ProjectTask.project_id == project_id
                    )
                )
                task_no = int(max_no.scalar() or 0) + 1
                candidate = ProjectTask(
                    id=gen_uuid(),
                    project_id=project_id,
                    member_id=member_id,
                    parent_id=parent_id,
                    status=status,
                    progress=0,
                    description=description or None,
                    type=task_type,
                    task_data={},
                    source=source,
                    source_ref=source_ref or {},
                    task_no=task_no,
                    origin_thread_id=origin_thread_id,
                    title=title,
                    priority=priority,
                    category=category,
                    tags=tags,
                    dependencies=dependencies,
                    acceptance_criteria=acceptance_criteria,
                    workflow_id=workflow_id,
                    workflow_round=workflow_round,
                    dispatch_count=0,
                    last_result=None,
                    last_error=None,
                    review_pending=False,
                    workflow_retry_count=0,
                    version=1,
                    risk_level=risk_level,
                    due_at=due_at,
                    trigger_spec=trigger,
                    dedup_key=dedup_key,
                    next_run_at=next_run_at,
                )
                session.add(candidate)
                try:
                    await session.flush()
                    task = candidate
                    break
                except IntegrityError:
                    # task_no 竞态或 dedup 并发重复：显式回滚清掉脏事务
                    # （session_scope 干净退出只 commit，脏 session 会让
                    # commit 抛 PendingRollbackError），下一轮循环重算
                    await session.rollback()
            if task is not None:
                break
            if _attempt < 2:
                await asyncio.sleep(0)
        if task is None:
            # 3 轮仍冲突：要么 dedup 并发重复（回读幂等），要么 task_no 竞态
            # 撞车——前者返回已有行，后者罕见到值得显式失败
            if dedup_key:
                existing = await TaskQueueService.get_by_dedup_key(dedup_key)
                if existing is not None:
                    return existing
            raise TaskQueueError(
                f"task creation conflict (task_no race) for project {project_id}"
            )
        notify_duty_wakeup()
        await publish_task_queue_event(task, event="task_created")
        return task

    @staticmethod
    async def get_by_dedup_key(dedup_key: str) -> ProjectTask | None:
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(ProjectTask).where(ProjectTask.dedup_key == dedup_key)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @staticmethod
    async def get_task_by_thread(thread_id: str) -> ProjectTask | None:
        """按运行线程反查任务（任务认领时落 last_thread_id，见 take）。

        回复路由用：wakeup 会话终态 → 任务 → source_ref 回复元数据。
        """
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(ProjectTask).where(ProjectTask.last_thread_id == thread_id)
            res = await session.execute(stmt)
            return res.scalars().first()

    @staticmethod
    async def get_task(task_id: str) -> ProjectTask | None:
        async with session_scope() as session:
            stmt = select(ProjectTask).where(ProjectTask.id == task_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @staticmethod
    async def get_subtasks_counts(parent_ids: list[str]) -> dict[str, dict[str, int]]:
        """Return {parent_id: {'total': N, 'completed': M}} for given parent task IDs."""
        if not parent_ids:
            return {}
        async with session_scope() as session:
            stmt = select(ProjectTask.parent_id, ProjectTask.status).where(
                ProjectTask.parent_id.in_(parent_ids)
            )
            res = await session.execute(stmt)
            counts: dict[str, dict[str, int]] = {
                pid: {"total": 0, "completed": 0} for pid in parent_ids
            }
            for pid, status in res.all():
                if pid and pid in counts:
                    counts[pid]["total"] += 1
                    if status == "completed":
                        counts[pid]["completed"] += 1
            return counts

    @staticmethod
    async def list_tasks(
        *,
        project_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
        source: str | None = None,
        due_before: datetime | None = None,
        root_only: bool = False,
        limit: int = 20,
        offset: int = 0,
        member_id: int | None = None,
        order: Literal["queue", "recent"] = "queue",
    ) -> list[ProjectTask]:
        """队列列表。``order``：
        - ``queue``：派发序（priority → due → category，supervisor 同款）
        - ``recent``：看板序（updated_at desc）——分页必须与最终展示序一致，
          路由层二次排序会破坏 offset 窗口的一致性
        """

        async with session_scope() as session:
            stmt = select(ProjectTask)
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            elif member_id is not None:
                stmt = stmt.where(TaskQueueService._member_task_filter(member_id))
            if status:
                stmt = stmt.where(ProjectTask.status == status)
            if source:
                stmt = stmt.where(ProjectTask.source == source)
            if category:
                stmt = stmt.where(ProjectTask.category == category)
            if due_before is not None:
                stmt = stmt.where(
                    (ProjectTask.due_at <= due_before)
                    | (ProjectTask.next_run_at <= due_before)
                )
            if root_only:
                stmt = stmt.where(ProjectTask.parent_id.is_(None))
            if order == "recent":
                stmt = stmt.order_by(
                    ProjectTask.updated_at.desc().nullslast(),
                    ProjectTask.created_at.desc(),
                )
            else:
                stmt = stmt.order_by(*_queue_ordering())
            stmt = stmt.offset(max(offset, 0)).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)

    @staticmethod
    async def take_task(task_id: str, thread_id: str) -> ProjectTask:
        """Claim a pending task for execution (atomic pending→in_progress).

        派发即认领（claim-then-persist）下，dispatcher 已在派发前完成系统侧
        认领并绑定同一 wakeup 线程——agent 的 take 变为幂等确认：同线程重复
        take 直接返回已认领任务；跨线程占用仍然拒绝。
        """
        current = await TaskQueueService.get_task(task_id)
        if current is not None and current.status == "in_progress":
            if (current.last_thread_id or "") == thread_id:
                return current  # 幂等：系统认领即绑定，无事件重复发布
            raise TaskQueueError(
                f"task {task_id} is already in progress on another thread"
            )

        async with session_scope() as session:
            stmt = (
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "pending",
                    ProjectTask.version == task_version(current),
                )
                .values(
                    status="in_progress",
                    last_thread_id=thread_id,
                    version=task_version(current) + 1,
                )
            )
            res = await session.execute(stmt)
            if res.rowcount == 0:
                raise TaskQueueError(
                    f"task {task_id} version conflict or is not claimable"
                )
        task = await TaskQueueService.get_task(task_id)
        assert task is not None
        await publish_task_queue_event(task, event="task_taken")
        return task

    # ── TaskRun 生命周期（过程记录层；写入内聚于此，禁止散落） ──

    @staticmethod
    async def open_task_run(
        task_id: str, thread_id: str, attempt: int
    ) -> TaskRun | None:
        """认领即开 run 行（running）。失败不阻断认领主路径（记录层降级）。"""
        from app.models.task_run import TaskRun

        try:
            async with session_scope() as session:
                run = TaskRun(
                    id=gen_uuid(),
                    task_id=task_id,
                    thread_id=thread_id,
                    attempt=max(attempt, 1),
                    status="running",
                )
                session.add(run)
                await session.flush()
                return run
        except Exception:
            logger.warning(
                "[TaskRuns] open run failed for task %s (non-fatal)",
                task_id,
                exc_info=True,
            )
            return None

    @staticmethod
    async def close_task_run(
        task_id: str,
        thread_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        result_summary: str | None = None,
    ) -> None:
        """终态化该任务当前线程的 run 行（幂等：只关未关闭的 running）。"""
        from app.models.task_run import TaskRun

        try:
            async with session_scope() as session:
                await session.execute(
                    update(TaskRun)
                    .where(
                        TaskRun.task_id == task_id,
                        TaskRun.thread_id == thread_id,
                        TaskRun.status == "running",
                    )
                    .values(
                        status=status,
                        finished_at=_now(),
                        error_code=error_code,
                        error_message=(
                            error_message[:RESULT_MAX] if error_message else None
                        ),
                        result_summary=(
                            result_summary[:RESULT_MAX] if result_summary else None
                        ),
                    )
                )
        except Exception:
            logger.warning(
                "[TaskRuns] close run failed for task %s (non-fatal)",
                task_id,
                exc_info=True,
            )

    @staticmethod
    async def list_task_runs(task_id: str, limit: int = 10) -> list[TaskRun]:
        """attempt 历史倒序（队列 API 内联 / 前端展示每次尝试）。"""
        from app.models.task_run import TaskRun

        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(TaskRun)
                        .where(TaskRun.task_id == task_id)
                        .order_by(TaskRun.attempt.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    @staticmethod
    async def claim_for_dispatch(task_id: str, thread_id: str) -> ProjectTask | None:
        """System-side claim at dispatch (pending→in_progress, atomic).

        派发即认领：one-shot 任务派发前落持久化占位（in_progress + 绑线程
        + dispatch_count 递增）。recurring 任务在真正被认领的同时才推进
        ``next_run_at``，避免「扫描候选时提前推进、后续实际未派发」导致任务
        被跳过（2026-09-24 mock 全量测试暴露）。

        修复「run 完成 × 任务仍 pending」被 DutyWakeupSubscriber 立即重派发
        的紧派发环。认领失败（并发/状态已变）返回 None，调用方跳过本轮。

        发布 ``task_taken``：认领即绑定时刻，前端看板语义与原 agent take 一致。
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            return None
        import time as _time

        claim_t0 = _time.monotonic()
        next_dispatch_count = task_dispatch_count(task) + 1
        version = task_version(task)

        update_values: dict[str, Any] = {
            "status": "in_progress",
            "last_thread_id": thread_id,
            "dispatch_count": next_dispatch_count,
            "version": version + 1,
        }
        # recurring 任务：真正认领成功时才推进 next_run_at
        if task.trigger_spec:
            from app.infrastructure.scheduler.service import SchedulerService

            update_values["next_run_at"] = SchedulerService.calculate_next_run(
                task.trigger_spec, _now()
            )

        async with session_scope() as session:
            res = await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "pending",
                    ProjectTask.version == version,
                )
                .values(**update_values)
            )
            if res.rowcount == 0:
                return None
        claimed = await TaskQueueService.get_task(task_id)
        assert claimed is not None
        # 过程记录：本次派发尝试开 run 行（attempt=dispatch_count）
        await TaskQueueService.open_task_run(task_id, thread_id, next_dispatch_count)
        await publish_task_queue_event(claimed, event="task_taken")
        logger.info(
            "[TaskQueueService] claim_for_dispatch took %.3fs (task=%s)",
            _time.monotonic() - claim_t0,
            task_id,
        )
        return claimed

    @staticmethod
    async def release_dispatch_claim(task_id: str, thread_id: str) -> None:
        """Rollback a dispatch claim (in_progress→pending) when dispatch failed.

        派发失败（DispatchStatus.FAILED / 派发异常）时回滚认领占位，任务回到
        队列由下一拍重试；``dispatch_count`` 保留——累计到
        ``DISPATCH_CLAIM_CIRCUIT_LIMIT`` 由熔断强制终态。不 notify_duty_wakeup：
        派发失败是确定性问题，立即重试只会形成无意义热循环，60s 兜底即可。

        对 recurring 任务，若 claim_for_dispatch 已推进 next_run_at，这里把它
        重置为 60s 后，确保失败任务能在近期重试，而不是被跳过到下一次 cron。
        """
        current = await TaskQueueService.get_task(task_id)
        if current is None:
            return
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "in_progress",
                    ProjectTask.last_thread_id == thread_id,
                    ProjectTask.version == task_version(current),
                )
                .values(
                    status="pending",
                    last_thread_id=None,
                    next_run_at=_now() + timedelta(seconds=60),
                    version=task_version(current) + 1,
                )
            )
        # 过程记录：派发失败回滚 → 本次 run 终态化（failed）
        await TaskQueueService.close_task_run(
            task_id,
            thread_id,
            status="failed",
            error_code="dispatch_failed",
            error_message="dispatch rolled back (will retry next drain cycle)",
        )

    @staticmethod
    async def advance_task(
        task_id: str,
        status: str,
        *,
        result: str | None = None,
        self_check: dict[str, Any] | None = None,
        by: str = "agent",
        thread_id: str | None = None,
    ) -> ProjectTask:
        """Move a task forward through the status machine.

        ``by`` marks the caller: "agent" (duty run) or "user" (board/confirm
        API). Proposals are only confirmable by the user — the executor run
        must never confirm its own proposal.
        """
        current = await TaskQueueService.get_task(task_id)
        if current is None:
            raise TaskQueueError(f"task {task_id} not found")
        if (
            thread_id is not None
            and current.last_thread_id is not None
            and current.last_thread_id != thread_id
        ):
            raise TaskQueueError(
                f"task {task_id} is bound to thread {current.last_thread_id}, not {thread_id}"
            )
        cur = current.status
        # 执行权隔离：提案的确认是用户决策（confirm API），Agent 只能推进
        if cur == "proposed" and by != "user":
            raise TaskQueueError(
                "proposed tasks are confirmed by the user, not the agent"
            )
        # 人体工学：Agent 常把 "任务做完了" 直接表达为 in_progress → completed。
        # 先把 completed 重定向为 self_checked（带 self_check 时与显式两步语义一致），
        # 避免无意义报错浪费轮次；随后再走下方 risk/origin 裁决终态。
        if cur == "in_progress" and status == "completed":
            status = "self_checked"
        # completed 必须留痕：干了什么、结果如何（先于转移合法性，错误信息更有用）
        if status == "completed" and not (result or "").strip():
            raise TaskQueueError("completed requires result (what was done, outcome)")
        # 人体工学（2026-09-25 实测：SDK 内核下 Agent 习惯携带完整 self_check
        # 一次性申请 waiting_acceptance，被状态机拒后经常弃收口直接文本收尾
        # → 回队重派空烧周期）。self_checked 本就是瞬态不落库——把
        # "in_progress + waiting_acceptance + 有效 self_check" 视作
        # self_checked 上报，终态由下方风险档逻辑裁决（机器决定，不由
        # Agent 指定），语义与两步走完全一致。
        if cur == "in_progress" and status == "waiting_acceptance" and self_check:
            status = "self_checked"
        if status not in QUEUE_TRANSITIONS.get(cur, ()):
            # 错误信息必须可行动：列出当前状态的合法目标，Agent 读到即可
            # 自我纠正（2026-09-25 实测：SDK 内核下 Agent 反复盲目跳转
            # in_progress→waiting_acceptance / pending→completed，每次非法
            # 跳转浪费 1-2 个重派周期逼近派发熔断——裸报 "illegal transition"
            # 无救场信息是直接诱因）。
            valid = QUEUE_TRANSITIONS.get(cur, ())
            hint = f"；{cur} 的合法目标: {', '.join(valid)}" if valid else ""
            raise TaskQueueError(f"illegal transition {cur} → {status}{hint}")

        # Acceptance pre-authorization on self-check (Agent reports done):
        # - T3/T4 with an origin conversation: NOT auto-completed — the result
        #   is pushed back to the origin dialogue for the reviewer (原对话
        #   Agent) to audit (reviewer:auto verdict drives completion). A
        #   waiting_acceptance row with task_data.review_pending=1 is "awaiting
        #   reviewer", distinct from T1/T2 human acceptance.
        # - No origin thread (board-created / workflow tasks): system
        #   auto-completes as before (no reviewer context to consult).
        # - T1/T2: waiting_acceptance (human decides).
        # - Missing/invalid risk: waiting_acceptance (fail closed).
        # self_checked is therefore a transient state, never persisted.
        effective = status
        review_requested = False
        if status == "self_checked":
            if current.trigger_spec:
                # recurring 任务：本轮正确终态是回队等下个周期（risk 闸门在
                # 每轮动作的 G4/HITL 层，不在轮次收口层——否则用户 accept 会
                # 把 completed 写成终态、巡检循环就此死亡）。
                effective = "pending"
            elif current.risk_level not in VALID_RISK_LEVELS:
                # one-shot 缺 risk：fail closed 等人验收，不再默认 T3 自动完成
                effective = "waiting_acceptance"
            else:
                risk = current.risk_level
                has_origin = bool(current.origin_thread_id)
                # requires_human_signoff：方向性决策产出（选品方向/定价/上架
                # 放行等）——评审者只能核验"做没做对"，不能替用户做商业判断，
                # 此类任务执行完挂"待人工验收"（与 T1/T2 同语义），人批准才
                # 解锁下游。
                needs_signoff = bool(
                    (current.task_data or {}).get("requires_human_signoff")
                )
                if risk in ("T3", "T4"):
                    if has_origin and not needs_signoff:
                        effective = "waiting_acceptance"
                        review_requested = True
                    else:
                        effective = (
                            "waiting_acceptance"
                            if (needs_signoff or risk in ("T1", "T2"))
                            else "completed"
                        )
                else:
                    effective = "waiting_acceptance"

        if effective == "completed" and not (result or "").strip():
            raise TaskQueueError("completed requires result (what was done, outcome)")

        values: dict[str, Any] = {
            "status": effective,
            "dispatch_count": 0,
            "version": task_version(current) + 1,
        }
        # 派发熔断计数重置：成功推进 = 本轮有实质进展，连续认领计数清零。
        # 否则 recurring 任务跨轮累计 dispatch_count，第 5 个 cron 会把健康
        # 周期任务误杀（2026-09-22 实测：售后 5 轮真实巡检全成功仍被熔断）。
        if result is not None:
            values["last_result"] = _clamp_result(result)
        if status == "self_checked":
            values["review_pending"] = review_requested
        if self_check is not None:
            values["self_check"] = self_check
        if effective == "completed" and not review_requested:
            values["acceptance"] = {
                "by": "system:auto",
                "at": _now().isoformat(),
                "verdict": "accepted",
                "risk": current.risk_level,
            }
        async with session_scope() as session:
            result_update = await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.version == task_version(current),
                )
                .values(**values)
            )
            if result_update.rowcount == 0:
                raise TaskQueueError(f"task {task_id} version conflict")
        # 转移留痕：每次状态推进记一行（from → to, by, thread）——并发派发
        # 场景下"任务在 run 活着时被错位回队"这类竞态靠它定位写入者
        # （2026-09-25 实测事故：错位回队真凶找不到，证据全靠猜）。
        logger.info(
            "[TaskQueue] advance: %s %s → %s (by=%s, task=%s)",
            cur,
            status,
            effective,
            by,
            task_id,
        )
        # 工作流聚合状态刷新：阶段任务每次状态推进都要回写所属 workflow
        # （否则 refresh_status 只在 growth 适配器路径被调，普通阶段任务
        # 终态后 workflow 永远停在 running → 周期 spawn 的 skip-on-busy
        # 判定永久忙）。失败不阻断任务推进（聚合层降级）。
        if str(task_workflow_id(current) or ""):
            try:
                from app.domain.tasks.workflows import WorkflowService

                await WorkflowService.refresh_status(str(task_workflow_id(current)))
            except Exception:
                logger.exception(
                    "[TaskQueue] workflow status refresh failed (workflow=%s)",
                    task_workflow_id(current),
                )
        # 过程记录：本轮 run 终态化（失败=failed；其余有效推进=succeeded，
        # 含 self_checked→waiting_acceptance/pending 回队——对任务而言非
        # 终态，但对"这一次派发尝试"而言是成功交付）
        run_thread = current.last_thread_id
        if run_thread:
            if effective == "failed":
                await TaskQueueService.close_task_run(
                    task_id,
                    run_thread,
                    status="failed",
                    error_message=result or None,
                )
            elif effective in (
                "completed",
                "waiting_acceptance",
                "pending",
                "cancelled",
            ):
                await TaskQueueService.close_task_run(
                    task_id,
                    run_thread,
                    status="succeeded",
                    result_summary=result,
                )
        if effective != status:
            # recurring 自检回队：立即唤醒 supervisor 接续下一轮
            notify_duty_wakeup()
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        await publish_task_queue_event(
            updated,
            event="task_advanced",
            extra={"requested_status": status, "effective_status": effective},
        )
        if review_requested:
            # 值守完成 → 回灌原对话，交由创建任务时的对话 Agent（评审者）
            # 以用户立场核验。异步触发，不阻塞 update_status 返回。
            from app.domain.tasks.review import trigger_review

            await trigger_review(updated)
        elif effective == "waiting_acceptance" and not review_requested:
            # signoff / T1/T2 等人拍板 → 推送手机触达（否则用户不开看板就
            # 无从知道链路停在自己这里）
            label = task_label(updated)
            title = task_title(updated) or ""
            await push_hitl_notice(
                updated,
                request_id=updated.id,
                kind="task_signoff",
                prompt=f"任务 {label}「{title[:40]}」执行完成，等你拍板（在看板验收，批准后链路继续）",
            )
        return updated

    @staticmethod
    async def find_review_pending_by_thread(origin_thread_id: str):
        """Task awaiting its reviewer verdict on the given origin thread."""
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            stmt = (
                select(ProjectTask)
                .where(
                    ProjectTask.origin_thread_id == origin_thread_id,
                    ProjectTask.status == "waiting_acceptance",
                )
                .order_by(ProjectTask.task_no.desc())
                .limit(1)
            )
            row = await session.execute(stmt)
            task = row.scalars().first()
        if task is None:
            return None
        if not task_review_pending(task):
            return None
        return task

    @staticmethod
    async def pending_requests_by_threads(
        thread_ids: list[str],
    ) -> dict[str, Any]:
        """pending HumanRequest → thread map（hitl-pending 与
        dashboard.awaiting_human 共用的单一查询，2026-09-25 收敛）。

        同线程多条 pending 时取最新一条（created_at desc）。
        """
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models.conversation import HumanRequest

        if not thread_ids:
            return {}
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(HumanRequest)
                        .where(
                            HumanRequest.status == "pending",
                            HumanRequest.thread_id.in_(thread_ids),
                        )
                        .order_by(HumanRequest.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        req_by_thread: dict[str, Any] = {}
        for req in rows:
            req_by_thread.setdefault(req.thread_id, req)
        return req_by_thread

    @staticmethod
    async def pending_hitl_requests(
        member_scope: int | None = None,
    ) -> list[dict[str, Any]]:
        """值守线程上的待处理 HITL 请求（`/tasks/queue/hitl-pending` 数据层）。

        覆盖三类线程：agent_*（growth 阶段 run）/ wakeup_*（值守 run）/
        duty_*（渠道值守）；原对话线程（origin_thread_id 上挂着
        review_pending 任务）一并纳入。多租户 fail-closed：无法归属到
        调用方的请求不暴露。
        """
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models import Repository
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
        origin_map: dict[str, ProjectTask] = {}
        for t in review_pending:
            if task_review_pending(t):
                origin_map[str(t.origin_thread_id)] = t

        candidate_thread_ids = [
            r.thread_id
            for r in rows
            if str(r.thread_id).startswith(prefixes) or str(r.thread_id) in origin_map
        ]
        tasks_map: dict[str, ProjectTask] = {}
        repo_member_map: dict[int, int] = {}
        if candidate_thread_ids:
            async with session_scope() as session:
                task_rows = (
                    (
                        await session.execute(
                            select(ProjectTask).where(
                                ProjectTask.last_thread_id.in_(candidate_thread_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                tasks_map = {t.last_thread_id: t for t in task_rows}
                project_ids = {
                    t.project_id
                    for t in list(tasks_map.values()) + list(origin_map.values())
                    if t and not t.member_id
                }
                if project_ids:
                    repo_rows = (
                        await session.execute(
                            select(Repository.project_id, Repository.member_id).where(
                                Repository.project_id.in_(project_ids)
                            )
                        )
                    ).all()
                    repo_member_map = {pid: int(mid or 0) for pid, mid in repo_rows}

        items: list[dict[str, Any]] = []
        for r in rows:
            is_origin_thread = str(r.thread_id) in origin_map
            if not str(r.thread_id).startswith(prefixes) and not is_origin_thread:
                continue
            task = (
                origin_map[str(r.thread_id)]
                if is_origin_thread
                else tasks_map.get(r.thread_id)
            )
            if member_scope is not None:
                if task is None:
                    continue  # fail-closed：无法归属的请求不暴露
                owner = task.member_id or repo_member_map.get(task.project_id or 0, 0)
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
        return items

    @staticmethod
    async def submit_acceptance(
        task_id: str,
        *,
        by: str,
        verdict: Literal["accepted", "rejected"],
        feedback: str = "",
    ) -> ProjectTask:
        """User acceptance. accepted → completed; rejected → pending (requeued).

        Rejected tasks carry the verdict + feedback in ``acceptance`` (surfaced
        to the Agent via `tasks list` and the wakeup payload) and re-enter the
        queue — the rework loop goes through dispatch, never stranded in
        in_progress.
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            raise TaskQueueError(f"task {task_id} not found")
        if task.status != "waiting_acceptance":
            raise TaskQueueError(
                f"task {task_id} not in waiting_acceptance (is {task.status})"
            )
        if verdict not in ("accepted", "rejected"):
            raise TaskQueueError(f"invalid acceptance verdict: {verdict}")
        if verdict == "accepted" and not (task_last_result(task) or "").strip():
            raise TaskQueueError("completed requires result (what was done, outcome)")
        receipt = {
            "by": by,
            "at": _now().isoformat(),
            "verdict": verdict,
            "feedback": feedback,
        }
        target = "completed" if verdict == "accepted" else "pending"

        # 评审收敛纪律：reviewer 不通过最多 2 轮。第 2 轮仍不通过 → 任务转
        # failed 并升级原对话"转人工仲裁"，杜绝"评审-返工"无限循环导致的
        # 执行者过度实施。人工（user）拒绝不受此限——用户的裁决权优先。
        if verdict == "rejected" and target == "pending":
            new_count = int(getattr(task, "review_count", 0) or 0) + 1
            if by.startswith("reviewer:") and new_count >= 2:
                target = "failed"
                receipt["escalated"] = True
            values_extra: dict[str, Any] = {}
            if by.startswith("reviewer:"):
                values_extra["review_count"] = new_count
        else:
            values_extra = {}

        async with session_scope() as session:
            values = {
                "acceptance": receipt,
                "status": target,
                "review_pending": False,
                "version": task_version(task) + 1,
                **values_extra,
            }
            result_update = await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "waiting_acceptance",
                    ProjectTask.version == task_version(task),
                )
                .values(**values)
            )
            if result_update.rowcount == 0:
                raise TaskQueueError(f"task {task_id} version conflict")
        # 工作流聚合状态刷新（同 advance_task：验收裁决改变阶段终态，
        # 所属 workflow 的 running/completed 聚合必须跟着走）。
        if str(task_workflow_id(task) or ""):
            try:
                from app.domain.tasks.workflows import WorkflowService

                await WorkflowService.refresh_status(str(task_workflow_id(task)))
            except Exception:
                logger.exception(
                    "[TaskQueue] workflow status refresh failed (workflow=%s)",
                    task_workflow_id(task),
                )
        if verdict == "rejected":
            if target == "failed":
                # 两轮评审未通过：升级原对话转人工仲裁（终态，不再回队）
                updated = await TaskQueueService.get_task(task_id)
                assert updated is not None
                from app.domain.tasks.review import notify_arbitration

                await notify_arbitration(updated, feedback)
                await publish_task_queue_event(
                    updated,
                    event="task_rejected",
                    extra={"by": by, "feedback": feedback},
                )
                return updated
            notify_duty_wakeup()
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        await publish_task_queue_event(
            updated,
            event="task_accepted" if verdict == "accepted" else "task_rejected",
            extra={"by": by, "feedback": feedback},
        )
        return updated

    @staticmethod
    async def resolve_member_id(task: ProjectTask) -> int:
        """多租户 fail-closed 的任务归属解析：task.member_id → repositories 回填。

        Project 无 SQL 模型（文件制），归属映射在 repositories 表
        （Repository.project_id → Repository.member_id）。单租户模式下
        member_id 恒 0，回填结果不影响。
        """
        if task.member_id:
            return int(task.member_id)
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models.codebase import Repository

        async with session_scope() as session:
            result = await session.execute(
                select(Repository.member_id).where(
                    Repository.project_id == (task.project_id or 0)
                )
            )
            member_id = result.scalar_one_or_none()
            return int(member_id or 0)

    @staticmethod
    @staticmethod
    def _member_task_filter(member_id: int):
        """多租户任务归属：member_id 列直配，或项目经 Repository 归属解析。"""
        from sqlalchemy import or_

        from app.models.codebase import Repository

        owned_projects = select(Repository.project_id).where(
            Repository.member_id == member_id
        )
        return or_(
            ProjectTask.member_id == member_id,
            ProjectTask.project_id.in_(owned_projects),
        )

    @staticmethod
    async def dashboard(project_id: int | None = None, member_id: int | None = None):
        """看板聚合（原 API 路由内的业务逻辑归位 service 层）。

        ``member_id``（多租户）与 ``project_id`` 同传时以 project_id 归属为准
        （路由层已对 project 做 404）；仅 member_id 时全局聚合按归属过滤。
        """
        from datetime import timedelta

        from sqlalchemy import func, select

        from app.domain.tasks.schemas import DashboardPayload
        from app.models.conversation import AgentActivity
        from app.utils.time import utcnow

        member_scope = (
            member_id if member_id is not None and project_id is None else None
        )

        activity_filter: list[Any] = []
        if project_id is not None:
            project_thread_ids = select(ProjectTask.last_thread_id).where(
                ProjectTask.project_id == project_id,
                ProjectTask.last_thread_id.isnot(None),
            )
            activity_filter = [AgentActivity.thread_id.in_(project_thread_ids)]
        elif member_scope is not None:
            member_thread_ids = select(ProjectTask.last_thread_id).where(
                TaskQueueService._member_task_filter(member_scope),
                ProjectTask.last_thread_id.isnot(None),
            )
            activity_filter = [AgentActivity.thread_id.in_(member_thread_ids)]

        counts: dict[str, int] = {}
        async with session_scope() as session:
            stmt = select(ProjectTask.status, func.count(ProjectTask.id)).group_by(
                ProjectTask.status
            )
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            elif member_scope is not None:
                stmt = stmt.where(TaskQueueService._member_task_filter(member_scope))
            rows = await session.execute(stmt)
            for st, n in rows:
                counts[st] = int(n)

        # duty state: busy if any task in_progress; error if failed in last 24h
        from app.core.channel.duty.config import load_global_duty_config

        duty_enabled = bool(load_global_duty_config().get("enabled"))
        duty_state = "idle"
        if counts.get("in_progress", 0) > 0:
            duty_state = "busy"
        async with session_scope() as session:
            since = utcnow() - timedelta(hours=24)
            scope_conds: list[Any] = []
            if project_id is not None:
                scope_conds.append(ProjectTask.project_id == project_id)
            elif member_scope is not None:
                scope_conds.append(TaskQueueService._member_task_filter(member_scope))
            failed_recent = await session.execute(
                select(func.count(ProjectTask.id)).where(
                    ProjectTask.status == "failed",
                    ProjectTask.updated_at >= since,
                    *scope_conds,
                )
            )
            if int(failed_recent.scalar() or 0) > 0:
                duty_state = "error"

        # tokens: today + this week from agent_activities (per-run rollup)
        week_tokens = {"input": 0, "output": 0, "llm_calls": 0}
        current_run = None
        today_window: dict[str, Any] = {"since": None, "until": None}

        now = utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=now.weekday())
        token_cols = (
            func.coalesce(func.sum(AgentActivity.input_tokens), 0),
            func.coalesce(func.sum(AgentActivity.output_tokens), 0),
            func.coalesce(func.sum(AgentActivity.llm_calls), 0),
        )

        # Today tokens
        async with session_scope() as session:
            res = await session.execute(
                select(*token_cols).where(
                    AgentActivity.updated_at >= day_start,
                    *activity_filter,
                )
            )
            r = res.one()
            today_tokens = {
                "input": int(r[0]),
                "output": int(r[1]),
                "llm_calls": int(r[2]),
            }

        # Week tokens
        async with session_scope() as session:
            res = await session.execute(
                select(*token_cols).where(
                    AgentActivity.updated_at >= week_start,
                    *activity_filter,
                )
            )
            r = res.one()
            week_tokens = {
                "input": int(r[0]),
                "output": int(r[1]),
                "llm_calls": int(r[2]),
            }

        # Today active window + currently running activity
        async with session_scope() as session:
            win = await session.execute(
                select(
                    func.min(AgentActivity.updated_at),
                    func.max(AgentActivity.updated_at),
                ).where(
                    AgentActivity.updated_at >= day_start,
                    *activity_filter,
                )
            )
            w = win.one()
            today_window = {
                "since": w[0].isoformat() if w[0] else None,
                "until": w[1].isoformat() if w[1] else None,
            }
            fresh_cutoff = utcnow() - timedelta(hours=2)
            running = await session.execute(
                select(AgentActivity).where(
                    AgentActivity.status == "running",
                    AgentActivity.updated_at >= fresh_cutoff,
                    *activity_filter,
                )
            )
            act = running.scalars().first()
            if act:
                current_run = {
                    "thread_id": act.thread_id,
                    "goal": (act.main_goal or "")[:80],
                    "started_at": act.updated_at.isoformat()
                    if act.updated_at
                    else None,
                    "input_tokens": int(act.input_tokens or 0),
                    "output_tokens": int(act.output_tokens or 0),
                }

        # 7-day daily aggregation for charts (tokens + completed tasks)
        daily_days: list[dict[str, Any]] = []
        async with session_scope() as session:
            now = utcnow()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = day_start - timedelta(days=6)
            tok_rows = await session.execute(
                select(
                    func.date(AgentActivity.updated_at).label("d"),
                    func.coalesce(func.sum(AgentActivity.input_tokens), 0),
                    func.coalesce(func.sum(AgentActivity.output_tokens), 0),
                )
                .where(AgentActivity.updated_at >= week_ago)
                .where(*activity_filter)
                .group_by(func.date(AgentActivity.updated_at))
            )
            tok_map = {
                str(r[0]): {"input": int(r[1]), "output": int(r[2])} for r in tok_rows
            }
            done_rows = await session.execute(
                select(
                    func.date(ProjectTask.updated_at).label("d"),
                    func.count(ProjectTask.id),
                )
                .where(
                    ProjectTask.status == "completed",
                    ProjectTask.updated_at >= week_ago,
                    *(
                        [ProjectTask.project_id == project_id]
                        if project_id is not None
                        else [TaskQueueService._member_task_filter(member_scope)]
                        if member_scope is not None
                        else []
                    ),
                )
                .group_by(func.date(ProjectTask.updated_at))
            )
            done_map = {str(r[0]): int(r[1]) for r in done_rows}
            for i in range(7):
                d = (week_ago + timedelta(days=i)).date()
                key = d.isoformat()
                tk = tok_map.get(key, {"input": 0, "output": 0})
                daily_days.append(
                    {
                        "date": key,
                        "input_tokens": tk["input"],
                        "output_tokens": tk["output"],
                        "completed": done_map.get(key, 0),
                    }
                )

        # event feed: recently touched tasks (newest first, max 10)
        recent_events: list[dict[str, Any]] = []
        async with session_scope() as session:
            stmt = select(ProjectTask).order_by(ProjectTask.updated_at.desc()).limit(10)
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            elif member_scope is not None:
                stmt = stmt.where(TaskQueueService._member_task_filter(member_scope))
            else:
                stmt = stmt.where(ProjectTask.project_id.isnot(None))
            for t in (await session.execute(stmt)).scalars().all():
                recent_events.append(
                    {
                        "at": t.updated_at.isoformat() if t.updated_at else None,
                        "kind": (
                            "proposal"
                            if t.status == "proposed"
                            else "acceptance"
                            if t.acceptance
                            else "progress"
                        ),
                        "title": task_title(t),
                        "status": t.status,
                        "task_id": t.id,
                        "result": (task_last_result(t) or "")[:120],
                    }
                )

        # awaiting_human: 挂起等人工决策的任务（线程上有 pending HumanRequest）
        # —— 值守信任纪律的可见性面：问人必须被看见、被回答。
        awaiting_human: list[dict[str, Any]] = []
        async with session_scope() as session:
            busy_tasks = (
                (
                    await session.execute(
                        select(ProjectTask).where(
                            ProjectTask.status == "in_progress",
                            ProjectTask.last_thread_id.isnot(None),
                            *(
                                [ProjectTask.project_id == project_id]
                                if project_id is not None
                                else [
                                    TaskQueueService._member_task_filter(member_scope)
                                ]
                                if member_scope is not None
                                else []
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if busy_tasks:
                thread_ids = [t.last_thread_id for t in busy_tasks]
                # pending HumanRequest 查询单一来源（hitl-pending 路由共用）
                req_by_thread = await TaskQueueService.pending_requests_by_threads(
                    thread_ids
                )
                for t in busy_tasks:
                    req = req_by_thread.get(t.last_thread_id or "")
                    if req is None:
                        continue
                    awaiting_human.append(
                        {
                            "task_id": t.id,
                            "title": task_title(t),
                            "thread_id": t.last_thread_id,
                            "question": (req.description or "")[:200],
                            "options": req.options or [],
                            "default_value": req.default_value,
                            "at": req.created_at.isoformat()
                            if req.created_at
                            else None,
                        }
                    )

        return DashboardPayload(
            counts=counts,
            duty_state=duty_state,
            duty_enabled=duty_enabled,
            tokens={"today": today_tokens, "week": week_tokens},
            today_window=today_window,
            current_run=current_run,
            daily=daily_days,
            recent_events=recent_events,
            awaiting_human=awaiting_human,
        )

    @staticmethod
    def require_in_project(task: ProjectTask, project_id: int | None) -> None:
        """项目隔离断言：task 必须属于 project_id（None = 全局模式不设限）。"""
        if project_id is not None and task.project_id != int(project_id):
            raise TaskQueueError(f"task {task.id} belongs to another project")

    @staticmethod
    async def requeue_stuck_task(task_id: str, reason: str) -> ProjectTask | None:
        """Reconcile move: park a stranded in_progress task back into the queue.

        Used by the duty supervisor when the run behind a task reached a
        terminal state without advancing the task (crash, lost run, agent
        dropped the ball). ``requeue_count`` in task_data bounds retries:
        after ``REQUEUE_LIMIT`` requeues the task fails with the reason
        recorded, so a poison task cannot loop forever.
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None or task.status != "in_progress":
            return None
        td = dict(task.task_data or {})
        count = int(td.get("requeue_count") or 0) + 1
        td["requeue_count"] = count
        target = "failed" if count > REQUEUE_LIMIT else "pending"
        version = task_version(task)
        async with session_scope() as session:
            result_update = await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "in_progress",
                    ProjectTask.version == version,
                )
                .values(
                    task_data=td,
                    status=target,
                    last_result=reason[:RESULT_MAX],
                    version=version + 1,
                )
            )
            if result_update.rowcount == 0:
                raise TaskQueueError(f"task {task_id} version conflict")
        # 过程记录：悬挂回队 → 本次 run 判失败（run 死了/没推进）
        if task.last_thread_id:
            await TaskQueueService.close_task_run(
                task_id,
                task.last_thread_id,
                status="failed",
                error_code="requeued_stuck",
                error_message=reason,
            )
        # 事件补全：reconciler 回队/判死此前静默无事件，UI（节点页收缩、
        # 看板刷新）完全无感知——按 advance 语义广播
        requeued = await TaskQueueService.get_task(task_id)
        if requeued is not None:
            await publish_task_queue_event(
                requeued,
                event="task_advanced",
                extra={"reason": reason[:120]},
            )
        notify_duty_wakeup()
        return requeued

    @staticmethod
    async def evaluate_dependency_gate(
        task: ProjectTask,
    ) -> tuple[bool, list[ProjectTask]]:
        """依赖门控（单一实现，2026-09-25 收敛：claim 扫描与 dispatcher 派发闸共用）。

        规则：
        - 无依赖 → 放行；
        - recurring 上游 = lineage-only 边：它没有 completed 终态（轮次完成
          回队 pending），不参与完成度 gating、失败不触发断链（血统与上游
          上下文注入仍生效）——否则提案子任务会被 recurring 父任务永久卡死；
        - 依赖缺失/删除 → 不放行（数据被清理时不放行，防孤儿任务乱跑）；
        - 非 recurring 上游全部 completed → 放行。

        返回 ``(satisfied, failed_upstreams)``：failed_upstreams 供派发侧
        触发断链告警（通知是表现层副作用，不进规则本体）。
        """
        dep_ids = task_dependencies(task)
        if not dep_ids:
            return True, []
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(ProjectTask.id, ProjectTask.status, ProjectTask.type).where(
                        ProjectTask.id.in_([str(d) for d in dep_ids])
                    )
                )
            ).all()
        status_by_id = {r[0]: r[1] for r in rows}
        recurring_ids = {r[0] for r in rows if r[2] == "recurring"}
        gate_ids = [str(d) for d in dep_ids if str(d) not in recurring_ids]
        failed_ids = [
            gate_id for gate_id in gate_ids if status_by_id.get(gate_id) == "failed"
        ]
        failed_upstreams: list[ProjectTask] = []
        if failed_ids:
            async with session_scope() as session:
                failed_upstreams = list(
                    (
                        await session.execute(
                            select(ProjectTask).where(ProjectTask.id.in_(failed_ids))
                        )
                    )
                    .scalars()
                    .all()
                )
        satisfied = all(status_by_id.get(d) == "completed" for d in gate_ids)
        return satisfied, failed_upstreams

    @staticmethod
    async def claim_due_tasks(now: datetime | None = None) -> list[ProjectTask]:
        """Scan due tasks for dispatch, ordered by priority → due → category.

        - one-shot: status=pending AND (due_at IS NULL -> dispatchable
          immediately, OR due_at <= now when a start time was given)
        - recurring: trigger_spec set AND next_run_at <= now
        - proposed / waiting_acceptance / terminal tasks are never dispatched.

        注意：recurring 任务的 next_run_at 推进不再在扫描候选时做，而是移到
        ``claim_for_dispatch`` 真正认领成功时，防止候选被扫描后实际未派发导致
        任务被跳过（2026-09-24 mock 全量测试暴露）。

        Each candidate is claimed in its own short DB session to avoid holding
        a connection across the entire dispatch window.
        """

        now = now or _now()
        from sqlalchemy import and_, or_

        # Phase 1: take a lightweight snapshot of candidate task IDs only
        candidate_ids: list[str] = []
        async with session_scope() as session:
            stmt = (
                select(ProjectTask.id)
                .where(
                    ProjectTask.status == "pending",
                    or_(
                        and_(
                            ProjectTask.trigger_spec.is_(None),
                            or_(
                                ProjectTask.due_at.is_(None),
                                ProjectTask.due_at <= now,
                            ),
                        ),
                        and_(
                            ProjectTask.trigger_spec.isnot(None),
                            ProjectTask.next_run_at <= now,
                        ),
                    ),
                )
                .order_by(*_queue_ordering())
            )
            candidate_ids = list((await session.execute(stmt)).scalars().all())

        # Phase 2: claim each candidate in a short session
        ready_rows: list[ProjectTask] = []
        for task_id in candidate_ids:
            try:
                async with session_scope() as session:
                    task = await session.get(ProjectTask, task_id)
                    if task is None or task.status != "pending":
                        continue

                    # 注意：recurring 任务的 next_run_at 推进已移到 claim_for_dispatch，
                    # 只在真正被认领时才推进，防止候选扫描后实际未派发导致任务被跳过。

                    # 依赖门控：单一实现（evaluate_dependency_gate），dispatcher
                    # 派发闸共用同一规则——历史上 claim 与 dispatcher 各写一份
                    # （含 recurring 豁免），改语义必须两处同步，2026-09-25 收敛。
                    (
                        satisfied,
                        _failed_up,
                    ) = await TaskQueueService.evaluate_dependency_gate(task)
                    if not satisfied:
                        continue

                    ready_rows.append(task)
            except Exception as e:
                logger.exception(f"[TaskQueue] Failed to claim task {task_id}: {e}")

        # Phase 3: duty switch filter (outside any DB session)
        if ready_rows:
            from app.core.channel.duty.config import load_duty_config

            by_project: dict[int, list[ProjectTask]] = {}
            for t in ready_rows:
                by_project.setdefault(t.project_id or 0, []).append(t)
            ready_rows = []
            for pid, group in by_project.items():
                if pid == 0:
                    ready_rows.extend(group)
                    continue
                cfg = await load_duty_config(pid)
                if not cfg or not cfg.get("enabled"):
                    logger.info(
                        "[TaskQueue] project %s 值守未启用，挂起 %d 个到期任务",
                        pid,
                        len(group),
                    )
                    continue
                ready_rows.extend(group)

        return ready_rows

    @staticmethod
    async def _validate_dependencies(
        task: ProjectTask, dependencies: list[str]
    ) -> list[str]:
        """依赖边界校验：去重/自依赖/存在性/同项目/环（DAG 不变量）。"""
        deps = [str(d) for d in dict.fromkeys(dependencies)]  # 去重保序
        if task.id in deps:
            raise TaskQueueError("task cannot depend on itself")
        if not deps:
            return []

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(ProjectTask.id, ProjectTask.project_id).where(
                        ProjectTask.id.in_(deps)
                    )
                )
            ).all()
        found = {r[0]: r[1] for r in rows}
        missing = [d for d in deps if d not in found]
        if missing:
            raise TaskQueueError(f"dependency task(s) not found: {missing}")
        cross_project = [d for d in deps if found[d] != task.project_id]
        if cross_project:
            raise TaskQueueError(
                f"cross-project dependencies not allowed: {cross_project}"
            )

        # 环检测：以新依赖表沿下游走，若回到自身即成环
        async with session_scope() as session:
            all_rows = (
                await session.execute(
                    select(ProjectTask.id, ProjectTask.dependencies).where(
                        ProjectTask.project_id == task.project_id
                    )
                )
            ).all()
        dep_map = {r[0]: list(r[1] or []) for r in all_rows}
        dep_map[task.id] = deps  # 模拟更新后的依赖表
        queue = list(deps)
        visited: set[str] = set()
        while queue:
            curr = queue.pop()
            if curr == task.id:
                raise TaskQueueError("dependency cycle detected")
            if curr in visited:
                continue
            visited.add(curr)
            queue.extend(dep_map.get(curr, []))
        return deps

    @staticmethod
    async def edit_task(
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        risk_level: str | None = None,
        task_type: str | None = None,
        due_at: datetime | None = None,
        clear_due_at: bool = False,
        trigger_spec: str | None = None,
        clear_trigger_spec: bool = False,
        dependencies: list[str] | None = None,
        cancel: bool = False,
    ) -> ProjectTask:
        """User-facing edit: field updates + optional cancel.

        Cancel is the only status move allowed to the user (all other status
        transitions stay system-driven); setting trigger_spec implies recurring.
        ``dependencies`` 替换式更新（画布连线持久化入口）：服务端兜底校验
        存在性 / 同项目 / 自依赖 / 环——前端拓扑检查只是体验层，不是边界。
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            raise TaskQueueError(f"task {task_id} not found")

        updates: dict[str, Any] = {}
        if cancel and task.status not in ("completed", "failed", "cancelled"):
            updates["status"] = "cancelled"
            if task.last_thread_id:
                try:
                    from app.core.engine.session.manager import session_manager

                    await session_manager.stop_agent(
                        task.last_thread_id, "task_cancelled"
                    )
                except Exception:
                    logger.warning(
                        "[TaskQueueService] failed to stop agent for cancelled task %s",
                        task_id,
                        exc_info=True,
                    )

        if dependencies is not None:
            updates["dependencies"] = await TaskQueueService._validate_dependencies(
                task, dependencies
            )
        if title is not None:
            normalized_title = str(title).strip()
            if not normalized_title:
                raise TaskQueueError("title is required")
            updates["title"] = normalized_title
        if priority is not None:
            updates["priority"] = _normalize_priority(priority)
        if description is not None:
            updates["description"] = description
        if risk_level is not None:
            updates["risk_level"] = _normalize_risk(risk_level)
        if task_type is not None:
            normalized_type = str(task_type).strip().lower()
            if normalized_type not in VALID_TASK_TYPES:
                raise TaskQueueError(f"invalid task type: {task_type}")
            if normalized_type == "recurring" and not (
                trigger_spec or task.trigger_spec
            ):
                raise TaskQueueError("recurring tasks require trigger_spec")
            updates["type"] = normalized_type
        if due_at is not None:
            if due_at <= _now():
                raise TaskQueueError("due_at must be in the future")
            updates["due_at"] = due_at
        elif clear_due_at:
            updates["due_at"] = None
        if trigger_spec is not None:
            updates["trigger_spec"] = trigger_spec
            updates["type"] = "recurring"
            from app.infrastructure.scheduler.service import SchedulerService

            updates["next_run_at"] = SchedulerService.calculate_next_run(
                trigger_spec, _now()
            )
        elif clear_trigger_spec:
            updates["trigger_spec"] = None
            updates["next_run_at"] = None
            updates["type"] = task_type or "once"

        if not updates:
            raise TaskQueueError("nothing to update")

        updates["version"] = task_version(task) + 1
        async with session_scope() as session:
            result_update = await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.version == task_version(task),
                )
                .values(**updates)
            )
            if result_update.rowcount == 0:
                raise TaskQueueError(f"task {task_id} version conflict")
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        if cancel and updated.status == "cancelled":
            await TaskQueueService._cancel_subtree(updated.id)
        await publish_task_queue_event(updated, event="task_updated")
        return updated

    @staticmethod
    async def _cancel_subtree(root_id: str) -> int:
        """根任务被用户取消 → 级联取消整棵子树。

        此前 cancel 只停任务自己的 agent，子任务变孤儿继续等派发。
        BFS 按 parent_id 遍历整棵子树：终态任务（completed/failed/
        cancelled）跳过取消但仍继续向下遍历（可能挂着非终态孙任务）；
        运行中的 agent 一并 stop；每个被取消任务按 advance 语义广播
        事件（UI 节点收缩/看板移除即时感知）。
        """
        terminal = ("completed", "failed", "cancelled")
        frontier = [root_id]
        cancelled = 0
        while frontier:
            parent_ids = frontier
            frontier = []
            async with session_scope() as session:
                rows = (
                    await session.execute(
                        select(
                            ProjectTask.id,
                            ProjectTask.status,
                            ProjectTask.last_thread_id,
                        ).where(ProjectTask.parent_id.in_(parent_ids))
                    )
                ).all()
            for tid, status, thread_id in rows:
                frontier.append(tid)
                if status in terminal:
                    continue
                async with session_scope() as session:
                    await session.execute(
                        update(ProjectTask)
                        .where(
                            ProjectTask.id == tid,
                            ProjectTask.status.notin_(terminal),
                        )
                        .values(status="cancelled", version=ProjectTask.version + 1)
                    )
                cancelled += 1
                if thread_id:
                    try:
                        from app.core.engine.session.manager import session_manager

                        await session_manager.stop_agent(thread_id, "task_cancelled")
                    except Exception:
                        logger.warning(
                            "[TaskQueueService] failed to stop agent for "
                            "cascade-cancelled task %s",
                            tid,
                            exc_info=True,
                        )
                t = await TaskQueueService.get_task(tid)
                if t is not None:
                    await publish_task_queue_event(
                        t,
                        event="task_advanced",
                        extra={"reason": "cascade_cancelled"},
                    )
        if cancelled:
            notify_duty_wakeup()
        return cancelled
