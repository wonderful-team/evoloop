"""派发即认领（claim-then-persist）回归测试。

AGENTS.md「自主值守（任务队列）关键事实」断裂修复记录 #6 的契约锁定：
- one-shot 任务派发前系统侧原子认领（pending→in_progress + last_thread_id
  + dispatch_count++），run 结束时任务必已被系统持有，杜绝「run 完成 ×
  任务仍 pending」被 DutyWakeupSubscriber 立即重派发的紧派发环；
- DispatchStatus.FAILED / 派发异常 → 认领回滚 pending，dispatch_count 保留；
- 认领次数达 DISPATCH_CLAIM_CIRCUIT_LIMIT → 熔断强制 failed，不再派发；
- take 幂等：同线程重复 take 视为已绑定；跨线程占用拒绝。
"""

from __future__ import annotations

import json as _json
from types import SimpleNamespace

import pytest
from sqlalchemy import update as sa_update

from app.domain.tasks.service import TaskQueueError, TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask


def _patch_engine(
    monkeypatch,
    captured: dict,
    tmp_path,
    *,
    dispatch_status: str = "QUEUED",
):
    """stub 引擎全链路：dispatch_agent_run / run_agent_background / 域表。"""
    from app.core.engine.dispatch import DispatchStatus

    status = getattr(DispatchStatus, dispatch_status)

    async def _fake_dispatch(**kwargs):
        captured.setdefault("dispatches", []).append(kwargs)
        return SimpleNamespace(
            status=status, inputs={"messages": []}, error=None
        )

    async def _fake_run(thread_id, _inputs):
        captured.setdefault("ran", []).append(thread_id)
        task_id = captured["dispatches"][-1]["metadata"]["source_task_id"]
        # 模拟 Agent 履约 take（派发即认领下为幂等确认）
        await TaskQueueService.take_task(task_id, thread_id)

    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
    )
    monkeypatch.setattr(
        "app.core.engine.agent.run_agent_background", _fake_run
    )
    monkeypatch.setattr(
        "app.core.engine.capability_profiles.list_domains", lambda _: []
    )

    proj_dir = tmp_path / "project-1"
    (proj_dir / ".evoloop").mkdir(parents=True, exist_ok=True)
    (proj_dir / ".evoloop" / "project.json").write_text(
        _json.dumps({"customer_service_duty": {"enabled": True}})
    )

    async def _fake_gpp(*_a, **_k):
        return str(proj_dir)

    monkeypatch.setattr("app.core.project.utils.get_project_path", _fake_gpp)
    monkeypatch.setattr(
        "app.core.channel.duty.config.get_project_path", _fake_gpp
    )


async def _mk_task(**kw) -> ProjectTask:
    return await TaskQueueService.create_task(
        project_id=1, member_id=5, title=kw.pop("title", "probe"), risk_level="T3", **kw
    )


async def _get(task_id: str) -> ProjectTask:
    t = await TaskQueueService.get_task(task_id)
    assert t is not None
    return t


@pytest.mark.asyncio
async def test_dispatch_claims_one_shot_task(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """派发前系统认领：in_progress + 绑线程 + dispatch_count=1；不再重派发。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t = await _mk_task(due_at=None)

    await dispatch_due_tasks()

    assert len(captured.get("dispatches", [])) == 1
    thread_id = captured["dispatches"][0]["thread_id"]
    after = await _get(t.id)
    assert after.status == "in_progress"
    assert after.last_thread_id == thread_id
    assert after.dispatch_count == 1

    # run 已结束、任务仍 in_progress（fake run 只 take）→ 二轮 drain 不再认领，
    # 由 reconcile「线程终态+in_progress」回队网收敛——紧派发环被构造性关断
    await dispatch_due_tasks()
    assert len(captured["dispatches"]) == 1


@pytest.mark.asyncio
async def test_dispatch_failure_rolls_back_to_pending(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """派发 FAILED → 认领回滚 pending，dispatch_count 保留供熔断累计。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path, dispatch_status="FAILED")

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t = await _mk_task(due_at=None)

    await dispatch_due_tasks()

    after = await _get(t.id)
    assert after.status == "pending"
    assert after.last_thread_id is None
    assert after.dispatch_count == 1

    # 回滚后下一拍重试（有界）：认领次数继续累计（1 失败 + 1 成功）
    _patch_engine(monkeypatch, captured, tmp_path)  # 恢复成功派发
    await dispatch_due_tasks()
    assert len(captured["dispatches"]) == 2
    after2 = await _get(t.id)
    assert after2.status == "in_progress"
    assert after2.dispatch_count == 2


@pytest.mark.asyncio
async def test_dispatch_circuit_breaker_forces_failed(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """认领次数达阈值：强制 failed，绝不进入派发（LLM 零消耗）。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t = await _mk_task(due_at=None)
    # 预置 4 次历史派发（如连续派发失败回滚），本次认领后达阈值 5
    async with session_scope() as session:
        await session.execute(
            sa_update(ProjectTask)
            .where(ProjectTask.id == t.id)
            .values(dispatch_count=4)
        )

    await dispatch_due_tasks()

    assert not captured.get("dispatches")  # 熔断：零派发
    after = await _get(t.id)
    assert after.status == "failed"
    assert "熔断" in str(after.last_result or "")


@pytest.mark.asyncio
async def test_take_task_idempotent_semantics(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """take 幂等：同线程重复 take 成功返回；跨线程/非 pending 拒绝。"""
    _ = tmp_path
    t = await _mk_task(due_at=None)

    # 系统认领 → take 同线程幂等成功
    claimed = await TaskQueueService.claim_for_dispatch(t.id, "wakeup_1_aaa")
    assert claimed is not None
    assert claimed.status == "in_progress"
    bound = await TaskQueueService.take_task(t.id, "wakeup_1_aaa")
    assert bound.id == t.id

    # 跨线程 take 被拒（另一 run 的执行权不可抢）
    with pytest.raises(TaskQueueError):
        await TaskQueueService.take_task(t.id, "wakeup_1_bbb")

    # 未认领的 pending 任务：take 走原原子路径
    t2 = await _mk_task(title="fresh")
    taken = await TaskQueueService.take_task(t2_id := t2.id, "wakeup_1_ccc")
    assert taken.status == "in_progress"
    assert taken.last_thread_id == "wakeup_1_ccc"

    # 认领原语对非 pending 返回 None（防御并发/状态已变）
    assert await TaskQueueService.claim_for_dispatch(t2_id, "wakeup_1_xxx") is None


@pytest.mark.asyncio
async def test_advance_resets_dispatch_count(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001
):
    """advance 成功 = 实质进展 → 熔断计数清零（recurring 跨轮误杀回归）。"""
    _ = tmp_path
    # once 任务：认领 dc=1 → agent 自检推进 → dc 重置
    t = await _mk_task(due_at=None)
    assert await TaskQueueService.claim_for_dispatch(t.id, "wakeup_1_d1")
    await TaskQueueService.take_task(t.id, "wakeup_1_d1")
    advanced = await TaskQueueService.advance_task(
        t.id, "self_checked", result="ok"
    )
    assert advanced.status == "completed"  # T3 无 origin → system:auto
    assert advanced.dispatch_count == 0

    # recurring 任务：self_checked → pending(回队)且 dc 重置；next_run_at 保留
    tr = await _mk_task(title="patrol-r", trigger_spec="interval:1800")
    claimed = await TaskQueueService.claim_for_dispatch(tr.id, "wakeup_1_d2")
    assert claimed is not None and claimed.status == "in_progress"
    advanced_r = await TaskQueueService.advance_task(
        tr.id, "self_checked", result="本轮无待办"
    )
    assert advanced_r.status == "pending"  # recurring 回队等下轮
    assert advanced_r.dispatch_count == 0
