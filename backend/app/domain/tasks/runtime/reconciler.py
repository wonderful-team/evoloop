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


async def _expire_stale_hitl_requests(max_age_hours: int = 24) -> int:
    """审批有时效：pending 超 24h 的请求自动取消。

    值守语义下操作员可能长期不在，无限挂起的审批会让任务永久阻塞。
    超时 = 放弃这次人工介入（默认拒绝），任务走失败/重跑路径。
    """
    from datetime import datetime, timedelta, timezone

    from app.models import HumanRequest
    from sqlalchemy import select, update

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(HumanRequest.id).where(
                        HumanRequest.status == "pending",
                        HumanRequest.created_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0
        result = await session.execute(
            update(HumanRequest)
            .where(
                HumanRequest.id.in_(rows),
                HumanRequest.status == "pending",
            )
            .values(status="cancelled", updated_at=datetime.now(timezone.utc))
        )
        count = int(result.rowcount or 0)
    if count:
        from app.domain.tasks.runtime.wakeup import notify_duty_wakeup

        notify_duty_wakeup()
    return count


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

    # 0) 评审挂死兜底：waiting_acceptance + review_pending 超时（评审 run
    #    死亡/HITL 挂起/无终态事件）→ 用空结论走评审接线（无结论 = 不通过），
    #    由 review 的 2 轮上限收敛，绝不永久悬挂。
    review_timeout = timedelta(minutes=30)
    async with session_scope() as session:
        review_rows = (
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
    # signoff / T1T2 等拍板超 24h → 手机再提醒一次（防任务悄悄停在
    # "等你拍板" 而用户毫无感知；不自动批准——拍板权在人）
    signoff_rows = [
        t
        for t in review_rows
        if not (t.task_data or {}).get("review_pending")
        and t.updated_at
        and (now - t.updated_at) > timedelta(hours=24)
    ]
    for t in signoff_rows:
        td = t.task_data or {}
        if td.get("signoff_reminded"):
            continue
        td["signoff_reminded"] = True
        from app.infrastructure.database.sql.database import session_scope as _ss
        from sqlalchemy import update as _u

        from app.models.project import ProjectTask as _PT

        async with _ss() as session:
            await session.execute(
                _u(_PT).where(_PT.id == t.id).values(task_data=td)
            )
        try:
            from app.core.channel.base import ChannelContext
            from app.core.channel.output.mobile_channel import MobileChannel
            from app.core.config import settings as _settings

            if _settings.MOBILE_SYNC_ENABLED:
                no = td.get("task_no")
                label = f"#T-{no}" if no else t.id[:8]
                await MobileChannel().send_hitl_request(
                    request_id=f"signoff-remind-{t.id}",
                    request_type="confirmation",
                    prompt=f"提醒：任务 {label}「{td.get('title', '')[:36]}」已等你拍板超过 24 小时，链路下游全部停摆",
                    ctx=ChannelContext(thread_id=t.origin_thread_id or t.id, project_id=t.project_id),
                    metadata={"kind": "signoff_reminder", "task_id": t.id},
                )
        except Exception:
            logger.exception("[DutyReconciler] signoff remind push failed")

    for t in review_rows:
        if not (t.task_data or {}).get("review_pending"):
            continue
        stale = t.updated_at and (now - t.updated_at) > review_timeout
        if not stale:
            continue
        logger.warning(
            "[DutyReconciler] review pending timeout: task=%s (updated_at=%s)",
            t.id,
            t.updated_at,
        )
        try:
            from app.domain.tasks.review import resolve_review_verdict

            await resolve_review_verdict(t.id, "")
            handled += 1
        except Exception:
            logger.exception(
                "[DutyReconciler] review timeout resolution failed for %s", t.id
            )


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
        elif status is ActivityStatus.HUMAN_INTERRUPT and tid not in hitl_threads:
            # 孤儿中断：Agent 挂起等人，但 pending 请求已不存在（被关/丢失）——
            # 没人能解除这个挂起，必须回队重跑，否则任务永久悬挂
            reason = "orphan human_interrupt (no pending request); auto-requeued"
        elif status in _SKIP_STATUSES:
            continue  # 在跑 / 停止中 / 等人决策（有 pending 请求）
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
