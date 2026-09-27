"""HITL 审批时效接线回归（2026-09-23 收敛）：

reconcile_stranded 开头先过期（pending HumanRequest 超 24h 自动取消 =
默认拒绝），再计算豁免集合——挂起任务在同一轮走判死/回队，不再被过期
审批永久豁免（此前 _expire_stale_hitl_requests 从未被调用，任务可被
无人应答的审批无限阻塞）。
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.domain.tasks.runtime import reconciler
from app.infrastructure.database.sql.database import session_scope
from app.models import AgentActivity, HumanRequest, ProjectTask  # noqa: F401
from app.utils.time import utcnow


async def _mk_suspended_task_with_stale_hitl(
    *, stale_hours: float, request_status: str = "pending"
) -> str:
    """in_progress 任务 + 挂起审批（可指定审批是否已过期）。"""
    from app.domain.tasks.service import TaskQueueService

    thread = f"wakeup_1_stale_{stale_hours}"
    t = await TaskQueueService.create_task(project_id=1, title="卡在审批")
    await TaskQueueService.take_task(t.id, thread)
    async with session_scope() as session:
        session.add(
            AgentActivity(
                thread_id=thread,
                status="human_interrupt",
                updated_at=utcnow() - timedelta(minutes=5),
            )
        )
        session.add(
            HumanRequest(
                id=f"hr-{stale_hours}-{request_status}",
                thread_id=thread,
                type="confirmation",
                description="是否放行",
                status=request_status,
                created_at=utcnow() - timedelta(hours=stale_hours),
            )
        )
        await session.flush()
    return t.id


async def _get_request(request_id: str) -> HumanRequest:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(HumanRequest).where(HumanRequest.id == request_id)
            )
        ).scalar_one()
    return row


@pytest.fixture
def _no_end_run(monkeypatch):
    async def _fake_end_run(_thread_id, _status, **_kw):
        return None

    monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)


@pytest.mark.asyncio
async def test_stale_hitl_expired_and_task_requeued_same_pass(
    _db, duty_enabled, _no_end_run  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """审批挂起超 24h：同一轮内过期 + 任务回队（接线前：任务永久豁免）。"""
    from app.domain.tasks.service import TaskQueueService

    tid = await _mk_suspended_task_with_stale_hitl(stale_hours=25)

    handled = await reconciler.reconcile_stranded()

    assert handled == 1
    req = await _get_request("hr-25-pending")
    assert req.status == "cancelled"  # 审批超时 = 默认拒绝
    fresh = await TaskQueueService.get_task(tid)
    assert fresh is not None and fresh.status == "pending"  # 回队


@pytest.mark.asyncio
async def test_fresh_hitl_still_exempts_task(_db, duty_enabled, _no_end_run):  # noqa: ARG001 — fixture 副作用放行项目闸
    """未过期的挂起审批：任务仍然豁免（等人决策是合法状态）。"""
    from app.domain.tasks.service import TaskQueueService

    tid = await _mk_suspended_task_with_stale_hitl(stale_hours=1)

    handled = await reconciler.reconcile_stranded()

    assert handled == 0
    fresh = await TaskQueueService.get_task(tid)
    assert fresh is not None and fresh.status == "in_progress"
    req = await _get_request("hr-1-pending")
    assert req.status == "pending"  # 未被误杀
