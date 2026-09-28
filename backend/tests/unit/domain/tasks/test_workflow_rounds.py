"""周期工作流轮次机制（触发/编排/执行三分离）单测。

覆盖：模板校验（环/未知依赖/乱序/非法触发器）、confirm 上膛、
spawn_round 依赖接线/幂等恢复、skip-on-busy、cancel 收敛、
阶段推进 → workflow 聚合状态联动（advance_task 内嵌 refresh）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.tasks.schemas import WorkflowStageSpec
from app.domain.tasks.service import TaskQueueService
from app.domain.tasks.workflows import WorkflowError, WorkflowService
from app.utils.time import utcnow


def _stages() -> list[WorkflowStageSpec]:
    return [
        WorkflowStageSpec(key="a", title="采集 A", risk_level="T4"),
        WorkflowStageSpec(key="b", title="采集 B", risk_level="T4"),
        WorkflowStageSpec(key="agg", title="汇总", risk_level="T3", deps=["a", "b"]),
        WorkflowStageSpec(key="draft", title="外联草稿", risk_level="T3", deps=["agg"]),
    ]


async def _create_and_arm(**overrides):
    params = {
        "project_id": 1,
        "title": "每日巡检流水线",
        "goal": "验证轮次编排",
        "trigger_spec": "0 9 * * *",
        "origin_thread_id": "conv_thread",
        "stages": _stages(),
    }
    params.update(overrides)
    workflow = await WorkflowService.create_workflow(**params)
    armed = await WorkflowService.confirm_workflow(workflow.id)
    return armed


async def _mark_due(workflow_id: str) -> None:
    """把触发时刻拨到过去（spawn_due_rounds 的到期语义）。"""
    from sqlalchemy import update

    from app.infrastructure.database.sql.database import session_scope
    from app.models.task_workflow import TaskWorkflow

    past = utcnow() - timedelta(minutes=1)
    async with session_scope() as session:
        await session.execute(
            update(TaskWorkflow)
            .where(TaskWorkflow.id == workflow_id)
            .values(next_run_at=past)
        )


async def _complete_stage(task_id: str) -> None:
    """把一个阶段任务推进到 completed（T3/T4 无 origin → 系统自动完成）。"""
    thread = f"agent_test_{task_id[:8]}"
    await TaskQueueService.take_task(task_id, thread)
    await TaskQueueService.advance_task(
        task_id,
        "self_checked",
        result="阶段完成",
        self_check={"verdict": "pass", "checks": [], "deviations": []},
        thread_id=thread,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_create_workflow_persists_template_proposed(_db):
    workflow = await WorkflowService.create_workflow(
        project_id=1,
        title="每日巡检流水线",
        goal="验证轮次编排",
        trigger_spec="0 9 * * *",
        origin_thread_id="conv_thread",
        stages=_stages(),
    )
    assert workflow.status == "proposed"
    assert workflow.round_no == 0
    assert workflow.trigger_spec == "0 9 * * *"
    template = workflow.inputs["stage_template"]
    assert [s["key"] for s in template] == ["a", "b", "agg", "draft"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_create_workflow_rejects_cycle_bad_order_unknown_and_bad_trigger(_db):
    cyclic = [
        WorkflowStageSpec(key="x", title="X", deps=["y"]),
        WorkflowStageSpec(key="y", title="Y", deps=["x"]),
    ]
    with pytest.raises(WorkflowError, match="cycle"):
        await WorkflowService.create_workflow(
            project_id=1, title="环", goal="g", stages=cyclic
        )

    bad_order = [
        WorkflowStageSpec(key="child", title="C", deps=["parent"]),
        WorkflowStageSpec(key="parent", title="P"),
    ]
    with pytest.raises(WorkflowError, match="listed before"):
        await WorkflowService.create_workflow(
            project_id=1, title="乱序", goal="g", stages=bad_order
        )

    unknown = [WorkflowStageSpec(key="a", title="A", deps=["ghost"])]
    with pytest.raises(WorkflowError, match="unknown stage"):
        await WorkflowService.create_workflow(
            project_id=1, title="悬空", goal="g", stages=unknown
        )

    with pytest.raises(WorkflowError, match="invalid trigger_spec"):
        await WorkflowService.create_workflow(
            project_id=1,
            title="坏触发器",
            goal="g",
            trigger_spec="not-a-cron",
            stages=_stages(),
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_confirm_arms_trigger_and_rejects_reconfirm(_db):
    armed = await _create_and_arm()
    assert armed.status == "armed"
    assert armed.next_run_at is not None

    with pytest.raises(WorkflowError, match="not proposed"):
        await WorkflowService.confirm_workflow(armed.id)


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_spawn_round_wires_real_dep_ids_and_marks_round(_db):
    armed = await _create_and_arm()
    spawned = await WorkflowService.spawn_round(armed.id)
    assert [t.title for t in spawned] == ["采集 A", "采集 B", "汇总", "外联草稿"]
    assert all(t.workflow_round == 1 for t in spawned)
    assert all(t.workflow_id == armed.id for t in spawned)
    # deps 是同轮真实任务 id（不是 stage key）
    assert spawned[2].dependencies == [spawned[0].id, spawned[1].id]
    assert spawned[3].dependencies == [spawned[2].id]
    assert all(
        t.source_ref["kind"] == "workflow_round" and t.source_ref["round"] == 1
        for t in spawned
    )
    fresh = await WorkflowService.get_workflow(armed.id)
    assert fresh.round_no == 1
    assert fresh.status == "running"
    # sqlite 驱动返回 naive datetime（UTC 语义），只断言存在与推进事实
    assert fresh.next_run_at is not None
    assert str(fresh.next_run_at) >= str(armed.next_run_at)


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_spawn_round_manual_second_call_creates_next_round(_db):
    workflow = await _create_and_arm()
    first = await WorkflowService.spawn_round(workflow.id)
    second = await WorkflowService.spawn_round(workflow.id)
    assert all(t.workflow_round == 1 for t in first)
    assert all(t.workflow_round == 2 for t in second)
    assert {t.id for t in first}.isdisjoint({t.id for t in second})


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_spawn_round_is_idempotent_on_crash_recovery(_db):
    """spawn 中途崩溃（round_no 未推进）后重跑：dedup 幂等返回同一轮。"""
    workflow = await _create_and_arm()
    first = await WorkflowService.spawn_round(workflow.id)
    # 模拟崩溃回滚：round_no/next_run_at 写回 0/None
    from sqlalchemy import update

    from app.infrastructure.database.sql.database import session_scope
    from app.models.task_workflow import TaskWorkflow

    async with session_scope() as session:
        await session.execute(
            update(TaskWorkflow)
            .where(TaskWorkflow.id == workflow.id)
            .values(round_no=0, status="armed", next_run_at=None)
        )
    recovered = await WorkflowService.spawn_round(workflow.id)
    assert {t.id for t in recovered} == {t.id for t in first}
    assert len(recovered) == 4


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_spawn_due_rounds_skips_busy_then_runs_when_free(_db):
    workflow = await _create_and_arm()
    await _mark_due(workflow.id)

    spawned_workflows = await WorkflowService.spawn_due_rounds()
    assert spawned_workflows == 1
    rows = await WorkflowService.list_round_tasks(workflow.id, 1)
    assert len(rows) == 4

    # 上一轮仍有活任务 → skip-on-busy（本拍不 spawn 新轮）
    await _mark_due(workflow.id)
    assert await WorkflowService.spawn_due_rounds() == 0
    assert await WorkflowService.list_round_tasks(workflow.id, 2) == []

    # 全阶段终态 → 轮次收口 → 下一拍 spawn 第二轮（同日追赶语义）
    for stage in rows:
        await _complete_stage(stage.id)
    refreshed = await WorkflowService.get_workflow(workflow.id)
    assert refreshed.status == "completed"  # advance 内嵌 refresh 已联动
    await _mark_due(workflow.id)
    assert await WorkflowService.spawn_due_rounds() == 1
    second_round = await WorkflowService.list_round_tasks(workflow.id, 2)
    assert [t.title for t in second_round] == ["采集 A", "采集 B", "汇总", "外联草稿"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_advance_task_refreshes_workflow_status(_db):
    workflow = await _create_and_arm()
    spawned = await WorkflowService.spawn_round(workflow.id)
    for stage in spawned:
        await _complete_stage(stage.id)
    refreshed = await WorkflowService.get_workflow(workflow.id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_cancel_workflow_cuts_trigger_and_live_stages(_db):
    workflow = await _create_and_arm()
    spawned = await WorkflowService.spawn_round(workflow.id)
    await _complete_stage(spawned[0].id)  # a 完成；b/agg/draft 仍活

    cancelled = await WorkflowService.cancel_workflow(workflow.id)
    assert cancelled.status == "cancelled"
    assert cancelled.next_run_at is None
    for stage in spawned[1:]:
        fresh = await TaskQueueService.get_task(stage.id)
        assert fresh is not None and fresh.status == "cancelled"
    # 已完成的阶段不被翻案
    done = await TaskQueueService.get_task(spawned[0].id)
    assert done is not None and done.status == "completed"
    # 已取消工作流不再 spawn
    await _mark_due(workflow.id)
    assert await WorkflowService.spawn_due_rounds() == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_spawn_round_advances_past_current_cycle_on_early_run(_db):
    """早期触发时，next_run_at 必须推进到下一个自然周期，防止到达预定时刻时同日重复触发。"""
    workflow = await _create_and_arm()
    # 确认后初始 next_run_at 在今天 08:00 UTC（或明天 08:00 UTC）
    assert workflow.next_run_at is not None
    initial_target = workflow.next_run_at

    # 实例化首轮
    spawned = await WorkflowService.spawn_round(workflow.id)
    assert len(spawned) == 4
    fresh = await WorkflowService.get_workflow(workflow.id)
    # 首轮生成后，next_run_at 必须严格推进，且大于初始 slot
    assert fresh.next_run_at is not None
    assert WorkflowService._to_utc(fresh.next_run_at) > WorkflowService._to_utc(initial_target)
