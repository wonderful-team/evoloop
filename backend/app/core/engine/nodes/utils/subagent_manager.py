"""Subagent lifecycle management — cancel, recover, aggregate helpers.

Design: docs/subagent-design.md §6.3 / §6.4 / §6.5.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.engine.worker_registry import worker_registry
from app.infrastructure.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.subagent import SubagentRun, SubagentStatus

logger = logging.getLogger(__name__)


async def _get_run(sub_tid: str) -> SubagentRun | None:
    async with session_scope() as session:
        stmt = select(SubagentRun).where(SubagentRun.thread_id == sub_tid)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _update_run(sub_tid: str, **fields) -> None:
    async with session_scope() as session:
        stmt = select(SubagentRun).where(SubagentRun.thread_id == sub_tid)
        run = (await session.execute(stmt)).scalar_one_or_none()
        if run:
            for k, v in fields.items():
                setattr(run, k, v)


async def cancel_subagent(parent_tid: str, sub_tid: str) -> bool:
    """Cancel a specific subagent (running / awaiting_a2a / awaiting_human)."""
    from app.core.monitoring.activity import activity_monitor

    run = await _get_run(sub_tid)
    if not run or run.status not in (
        SubagentStatus.RUNNING,
        SubagentStatus.AWAITING_A2A,
        SubagentStatus.AWAITING_HUMAN,
    ):
        return False

    # Synchronize activity_monitor so late callbacks auto-drop via check_cancellation.
    await activity_monitor.stop_run(sub_tid)
    await worker_registry.cancel_worker(sub_tid)

    if run.status == SubagentStatus.AWAITING_HUMAN:
        from app.core.engine.nodes.utils.subagent_hitl import clear_subagent_hitl_route

        await clear_subagent_hitl_route(parent_tid, sub_tid)

    await _update_run(sub_tid, status=SubagentStatus.CANCELLED)
    return True


async def cancel_all_subagents(parent_tid: str) -> int:
    """Cancel all subagents of a parent (running / awaiting_a2a / awaiting_human)."""
    async with session_scope() as session:
        stmt = select(SubagentRun).where(
            SubagentRun.parent_thread_id == parent_tid,
            SubagentRun.status.in_(
                (
                    SubagentStatus.RUNNING,
                    SubagentStatus.AWAITING_A2A,
                    SubagentStatus.AWAITING_HUMAN,
                )
            ),
        )
        runs = (await session.execute(stmt)).scalars().all()

    count = 0
    for run in runs:
        if await cancel_subagent(parent_tid, run.thread_id):
            count += 1
    return count


async def recover_subagent_state(parent_tid: str) -> dict:
    """Recover subagent state from the SubagentRun table after process restart.

    First reaps stale running/awaiting records older than SUBAGENT_STALE_AFTER_SECONDS
    (their asyncio tasks died with the process), then returns active + completed.
    """
    # DB 未初始化（嵌入式单测等底座未就绪环境）→ 无表可调和，返回空避免误伤。
    if not db_resource_manager.is_ready:
        return {"active_subagents": [], "completed_subagents": []}

    from datetime import timedelta

    from app.core.config import settings

    reap_cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=getattr(settings, "SUBAGENT_STALE_AFTER_SECONDS", None) or 3600
    )
    async with session_scope() as session:
        # 进程重启后 worker_registry 为空 → 运行中的 subagent 的 asyncio task 已死，
        # 立即标记 failed/orphaned（不再等 1h stale 截止）。正常运行时 task 存活，
        # 仅当超过 stale 截止才回收。
        running_stmt = select(SubagentRun).where(
            SubagentRun.parent_thread_id == parent_tid,
            SubagentRun.status.in_(
                (
                    SubagentStatus.RUNNING,
                    SubagentStatus.AWAITING_A2A,
                    SubagentStatus.AWAITING_HUMAN,
                )
            ),
        )
        running = (await session.execute(running_stmt)).scalars().all()
        for r in running:
            rec = await worker_registry.get_worker(r.thread_id)
            task_alive = (
                rec is not None and rec.task is not None and not rec.task.done()
            )
            # SQLite 读回的时间无时区 → 按 UTC 解释后与 aware cutoff 比较。
            started = r.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if (not task_alive) or (started < reap_cutoff):
                r.status = SubagentStatus.FAILED
                r.error = (
                    f"orphaned: 进程重启后 subagent task 丢失（原状态 {r.status}）"
                )
                logger.warning(
                    f"[SubagentManager] Reaped orphaned subagent {r.id} -> failed"
                )
        await session.commit()

        stmt = select(SubagentRun).where(SubagentRun.parent_thread_id == parent_tid)
        runs = (await session.execute(stmt)).scalars().all()

    active, completed = [], []
    for r in runs:
        if r.status in (
            SubagentStatus.RUNNING,
            SubagentStatus.AWAITING_A2A,
            SubagentStatus.AWAITING_HUMAN,
        ):
            active.append(
                {
                    "subagent_id": r.id,
                    "thread_id": r.thread_id,
                    "instruction": r.instruction,
                    "status": r.status,
                }
            )
        elif r.status in (
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.CANCELLED,
        ):
            completed.append(
                {
                    "subagent_id": r.id,
                    "status": r.status,
                    "result": r.result or "",
                    "error": r.error,
                }
            )
    return {"active_subagents": active, "completed_subagents": completed}
