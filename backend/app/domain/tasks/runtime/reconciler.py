"""Duty reconciler — 值守死亡现场收敛（domain 层）。

职责：把"run 已死但任务/活动还悬着"的世界状态收敛回队列语义：
1) `wakeup_`/`agent_` 线程悬挂 running → 判死（startup 时一律判死，稳态超期 + 无等人豁免）；
2) `wakeup_`/`agent_` 线程已终态但任务仍 in_progress → 回队（requeue_count 上限防毒任务）。

只碰 `wakeup_`（wakeup run）与 `agent_`（workflow 阶段 run）前缀线程：两者
均为本进程 supervisor/workflow 引擎派生的值守 run，进程内死亡判定对本进程
语义成立；严禁触碰用户/其他通道线程。等人决策（pending HumanRequest /
HUMAN_INTERRUPT 挂起）是合法状态，一律豁免。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.monitoring.constants import ActivityStatus
from app.domain.tasks.constants import (
    NO_ACTIVITY_GRACE_SECONDS,
    QUOTA_COOLDOWN_MINUTES,
    RESTART_GRACE_SECONDS,
    RUN_SKIP_STATUSES,
    RUN_TERMINAL_STATUSES,
    STALE_RUNNING_MINUTES,
)
from app.domain.tasks.service import (
    TaskQueueService,
    task_review_pending,
    task_title,
)
from app.infrastructure.database.sql.database import session_scope

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset(ActivityStatus(v) for v in RUN_TERMINAL_STATUSES)
# 这些状态下任务现场仍在推进/等待，不得回队
_SKIP_STATUSES = frozenset(ActivityStatus(v) for v in RUN_SKIP_STATUSES)


async def _supervisor_end_run(thread_id: str, status: ActivityStatus, **kwargs):
    """end_run 间接层：单出口判死；测试可 monkeypatch（绕过事件总线/DB 依赖）。"""
    from app.core.monitoring.activity import activity_monitor

    return await activity_monitor.end_run(thread_id, status, **kwargs)


async def _pending_hitl_threads() -> set[str]:
    """有 pending HumanRequest 的值守线程集合（等人决策，豁免判死/回队）。

    wakeup_（wakeup run）与 agent_（workflow 阶段 run）同为本进程派生的
    值守线程——两者的 HITL 挂起都应豁免判死。
    """
    from sqlalchemy import or_

    from app.models import HumanRequest

    async with session_scope() as session:
        rows = await session.execute(
            select(HumanRequest.thread_id).where(
                HumanRequest.status == "pending",
                or_(
                    HumanRequest.thread_id.like("wakeup_%"),
                    HumanRequest.thread_id.like("agent_%"),
                ),
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

    from sqlalchemy import select, update

    from app.models import HumanRequest

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
    from app.infrastructure.database.sql.database import session_scope
    from app.models import AgentActivity, ProjectTask

    now = datetime.now(timezone.utc)
    grace = (
        timedelta(seconds=RESTART_GRACE_SECONDS)
        if startup
        else timedelta(minutes=STALE_RUNNING_MINUTES)
    )
    # -1) 审批时效兜底：pending HumanRequest 超 24h 自动取消（默认拒绝），
    #     让挂起任务在本轮就走判死/回队——先过期再算豁免集合，同一轮收敛。
    try:
        expired = await _expire_stale_hitl_requests()
        if expired:
            logger.info(
                "[DutyReconciler] 过期 HITL 请求自动取消 %s 条（>24h 无人应答）",
                expired,
            )
    except Exception:
        logger.exception("[DutyReconciler] HITL 过期清理失败（下一轮重试）")
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
        if not task_review_pending(t)
        and _aware(t.updated_at) is not None
        and now - _aware(t.updated_at) > timedelta(hours=24)
    ]
    for t in signoff_rows:
        td = t.task_data or {}
        if td.get("signoff_reminded"):
            continue
        td["signoff_reminded"] = True
        from sqlalchemy import update as _u

        from app.infrastructure.database.sql.database import session_scope as _ss
        from app.models.project import ProjectTask as _PT

        async with _ss() as session:
            await session.execute(_u(_PT).where(_PT.id == t.id).values(task_data=td))
        from app.domain.tasks.notify import push_hitl_notice, task_label

        label = task_label(t)
        await push_hitl_notice(
            t,
            request_id=f"signoff-remind-{t.id}",
            kind="signoff_reminder",
            prompt=f"提醒：任务 {label}「{(task_title(t) or '')[:36]}」已等你拍板超过 24 小时，链路下游全部停摆",
        )

    for t in review_rows:
        if not task_review_pending(t):
            continue
        # sqlite 驱动返回 naive datetime（UTC 语义）：直接与 aware now 相减
        # 会 TypeError 并整个 reconcile 中断（HITL 过期/判死/回队全灭），
        # 必须经 _aware 归一（2026-09-24 实测事故）。
        stale = (
            _aware(t.updated_at) is not None
            and now - _aware(t.updated_at) > review_timeout
        )
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

    # 1) 悬挂 running/stopping 判死（wakeup_ 与 agent_ 同权：workflow 阶段
    #    run 同为本进程派生，进程死亡后其 activity 永久悬挂、任务永久
    #    in_progress——审计 F-05 实锤缺口）
    #    stopping = 协作取消已请求、等待 run_scope 收尾出终态；若进程死亡
    #    （重启/崩溃）收尾永远不会发生 → 僵尸 stopping 既不匹配 running 判死
    #    也不匹配终态回队，任务永久悬挂（2026-09-21 实测：值守急停后重启，
    #    4 个 stopping 僵尸卡死 4 条 in_progress 任务）。陈旧 stopping 与
    #    陈旧 running 同权判死。
    from sqlalchemy import or_

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(AgentActivity).where(
                        AgentActivity.status.in_(
                            [
                                ActivityStatus.RUNNING.value,
                                ActivityStatus.STOPPING.value,
                            ]
                        ),
                        or_(
                            AgentActivity.thread_id.like("wakeup_%"),
                            AgentActivity.thread_id.like("agent_%"),
                        ),
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
            "[DutyReconciler] 判死悬挂 %s: thread=%s (updated_at=%s)",
            act.status,
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
    duty_tasks = [
        t for t in tasks if str(t.last_thread_id).startswith(("wakeup_", "agent_"))
    ]
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
            # 认领（in_progress + 绑线程）→ run 启动（activity 落库）之间有
            # 秒级窗口：reconciler 恰好扫过窗口时，"无 activity 记录"不代表
            # run 已死。稳态下给宽限期，防止刚认领的任务被误杀回队（然后
            # 重派→再误杀→熔断 failed，2026-09-24 实测事故链）。
            # startup 时进程刚死，宽限期无意义（遗留 running 一律判死）。
            if not startup:
                claimed_at = _aware(t.updated_at)
                if claimed_at is not None and now - claimed_at < timedelta(
                    seconds=NO_ACTIVITY_GRACE_SECONDS
                ):
                    continue
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
