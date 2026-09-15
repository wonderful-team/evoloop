"""Duty reconciler — 值守死亡现场收敛（domain 层）。

职责：把"run 已死但任务/活动还悬着"的世界状态收敛回队列语义：
1) `wakeup_` 线程悬挂 running → 判死（startup 时一律判死，稳态超期 + 无等人豁免）；
2) `wakeup_` 线程已终态但任务仍 in_progress → 回队（requeue_count 上限防毒任务）。

只碰 `wakeup_` 前缀线程：进程内死亡判定仅对本进程语义成立，严禁触碰
用户/其他通道线程。等人决策（pending HumanRequest / HUMAN_INTERRUPT 挂起）
是合法状态，一律豁免。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.monitoring.constants import ActivityStatus
from app.domain.tasks.constants import (
    QUOTA_COOLDOWN_MINUTES,
    RESTART_GRACE_SECONDS,
    RUN_SKIP_STATUSES,
    RUN_TERMINAL_STATUSES,
    STALE_RUNNING_MINUTES,
)

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset(
    ActivityStatus(v) for v in RUN_TERMINAL_STATUSES
)
# 这些状态下任务现场仍在推进/等待，不得回队
_SKIP_STATUSES = frozenset(ActivityStatus(v) for v in RUN_SKIP_STATUSES)


async def _supervisor_end_run(thread_id: str, status: ActivityStatus, **kwargs):
    """end_run 间接层：单出口判死；测试可 monkeypatch（绕过事件总线/DB 依赖）。"""
    from app.core.monitoring.activity import activity_monitor

    return await activity_monitor.end_run(thread_id, status, **kwargs)


async def _pending_hitl_threads() -> set[str]:
    """有 pending HumanRequest 的值守线程集合（等人决策，豁免判死/回队）。"""
    from app.infrastructure.database.sql.database import session_scope
    from app.models import HumanRequest

    async with session_scope() as session:
        rows = await session.execute(
            select(HumanRequest.thread_id).where(
                HumanRequest.status == "pending",
                HumanRequest.thread_id.like("wakeup_%"),
            )
        )
        return {r[0] for r in rows}


def _aware(dt: datetime | None) -> datetime | None:
    """sqlite 驱动返回 naive datetime（UTC 语义），统一归一为 aware 再比较。"""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def reconcile_stranded(*, startup: bool = False) -> int:
    """收敛死亡现场，返回处置的任务数。"""
    from app.domain.tasks.service import TaskQueueService
    from app.infrastructure.database.sql.database import session_scope
    from app.models import AgentActivity, ProjectTask

    now = datetime.now(timezone.utc)
    grace = (
        timedelta(seconds=RESTART_GRACE_SECONDS)
        if startup
        else timedelta(minutes=STALE_RUNNING_MINUTES)
    )
    hitl_threads = await _pending_hitl_threads()
    handled = 0

    # 1) 悬挂 running 判死
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(AgentActivity).where(
                        AgentActivity.status == ActivityStatus.RUNNING.value,
                        AgentActivity.thread_id.like("wakeup_%"),
                    )
                )
            )
            .scalars()
            .all()
        )
    stale = [
        a
        for a in rows
        if a.thread_id not in hitl_threads
        and _aware(a.updated_at) is not None
        and now - _aware(a.updated_at) > grace
    ]
    for act in stale:
        logger.warning(
            "[DutyReconciler] 判死悬挂 running: thread=%s (updated_at=%s)",
            act.thread_id,
            act.updated_at,
        )
        try:
            await _supervisor_end_run(
                act.thread_id,
                ActivityStatus.FAILED,
                final_outcome="watchdog: run lost (no terminal event)",
            )
        except Exception:
            logger.exception("[DutyReconciler] end_run failed for %s", act.thread_id)

    # 2) 终态线程上的悬置任务回队
    async with session_scope() as session:
        tasks = (
            (
                await session.execute(
                    select(ProjectTask).where(
                        ProjectTask.status == "in_progress",
                        ProjectTask.last_thread_id.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    duty_tasks = [t for t in tasks if str(t.last_thread_id).startswith("wakeup_")]
    if not duty_tasks:
        return handled

    thread_ids = {t.last_thread_id for t in duty_tasks}
    async with session_scope() as session:
        acts = (
            (
                await session.execute(
                    select(AgentActivity).where(AgentActivity.thread_id.in_(thread_ids))
                )
            )
            .scalars()
            .all()
        )
    status_by_thread: dict[str, str] = {a.thread_id: a.status for a in acts}

    for t in duty_tasks:
        tid = str(t.last_thread_id)
        if tid in hitl_threads:
            continue  # 等人决策，豁免
        raw_status = status_by_thread.get(tid)
        try:
            status = ActivityStatus(raw_status) if raw_status else None
        except ValueError:
            status = None

        if status is None:
            reason = "run lost (no activity record); auto-requeued by duty reconciler"
        elif status in _SKIP_STATUSES:
            continue  # 在跑 / 停止中 / 等人决策
        elif status not in _TERMINAL_STATUSES and status is not ActivityStatus.IDLE:
            continue
        else:
            reason = f"run {status.value}; auto-requeued by duty reconciler"
            if status is ActivityStatus.QUOTA_EXHAUSTED:
                # 配额熔断：暂停派发，避免串行 drain 把队列挨个打 429
                from app.domain.tasks.runtime.dispatcher import pause_duty_for

                pause_duty_for(QUOTA_COOLDOWN_MINUTES)

        updated = await TaskQueueService.requeue_stuck_task(t.id, reason)
        if updated is not None:
            handled += 1
            logger.info(
                "[DutyReconciler] 悬置任务回队: task=%s run=%s → %s",
                t.id,
                status.value if status else "lost",
                updated.status,
            )
    return handled
