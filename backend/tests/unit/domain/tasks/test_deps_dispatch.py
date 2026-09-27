"""Dependency-aware dispatch gating: upstream tasks gate downstream claims."""

from __future__ import annotations

import json as _json

import pytest
from sqlalchemy import update

from app.domain.tasks.service import TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask


async def _mark_completed(task_id: str) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ProjectTask)
            .where(ProjectTask.id == task_id)
            .values(status="completed")
        )


def _patch_engine(monkeypatch, captured: dict, tmp_path):
    from types import SimpleNamespace

    from app.core.engine.dispatch import DispatchStatus

    async def _fake_dispatch(**kwargs):
        captured.setdefault("dispatches", []).append(kwargs)
        return SimpleNamespace(
            status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
        )

    async def _fake_run(thread_id, _inputs):
        captured.setdefault("ran", []).append(thread_id)
        task_id = captured["dispatches"][-1]["metadata"]["source_task_id"]
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
    (proj_dir / ".evoloop").mkdir(parents=True)
    (proj_dir / ".evoloop" / "project.json").write_text(
        _json.dumps({"customer_service_duty": {"enabled": True}})
    )

    async def _fake_gpp(*_a, **_k):
        return str(proj_dir)

    monkeypatch.setattr("app.core.project.utils.get_project_path", _fake_gpp)
    monkeypatch.setattr(
        "app.core.channel.duty.config.get_project_path", _fake_gpp
    )


@pytest.mark.asyncio
async def test_dispatch_gates_on_dependencies(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001 — fixture 副作用放行项目闸
):
    """上游未完成时下游不派发；上游完成后按依赖顺序认领。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t1 = await TaskQueueService.create_task(
        project_id=183, title="上游", description="d", risk_level="T3"
    )
    t2 = await TaskQueueService.create_task(
        project_id=183, title="下游", description="d", risk_level="T3"
    )
    # 写依赖（依赖为一等列；test 环境直接更新列）
    async with session_scope() as session:
        await session.execute(
            update(ProjectTask)
            .where(ProjectTask.id == t2.id)
            .values(dependencies=[t1.id])
        )

    # 第一轮：上游 pending → 只派发上游，下游被依赖 gate
    await dispatch_due_tasks()
    dispatched = [d["metadata"]["source_task_id"] for d in captured.get("dispatches", [])]
    assert t1.id in dispatched
    assert t2.id not in dispatched

    # 模拟上游完成（直接置 completed）
    await _mark_completed(t1.id)

    # 第二轮：下游应被派发
    await dispatch_due_tasks()
    dispatched = [d["metadata"]["source_task_id"] for d in captured.get("dispatches", [])]
    assert t2.id in dispatched


@pytest.mark.asyncio
async def test_deps_missing_task_blocks(_db, monkeypatch, tmp_path, duty_enabled):  # noqa: ARG001
    """依赖任务被清理（不存在）→ 视为不满足，不放行。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t2 = await TaskQueueService.create_task(
        project_id=183, title="孤儿下游", description="d", risk_level="T3"
    )
    async with session_scope() as session:
        await session.execute(
            update(ProjectTask)
            .where(ProjectTask.id == t2.id)
            .values(dependencies=["00000000-0000-0000-0000-000000000000"])
        )

    await dispatch_due_tasks()
    dispatched = [d["metadata"]["source_task_id"] for d in captured.get("dispatches", [])]
    assert t2.id not in dispatched


@pytest.mark.asyncio
async def test_recurring_upstream_does_not_gate(_db, monkeypatch, tmp_path, duty_enabled):  # noqa: ARG001
    """recurring 上游没有 completed 终态（轮次完成回队 pending）：对它的
    依赖按 lineage-only 边处理，不 gate 派发——否则 Agent 在 recurring
    巡检里提的案子被父任务永久卡死。"""
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    t1 = await TaskQueueService.create_task(
        project_id=183,
        title="每日巡检父任务",
        description="d",
        risk_level="T3",
        type="recurring",
        trigger_spec="0 9 * * *",
    )
    # 提案子任务：带 parent_id 创建，依赖自动回填父任务
    t2 = await TaskQueueService.create_task(
        project_id=183, title="巡检提案子任务", description="d", risk_level="T3",
        parent_id=t1.id,
    )
    assert (t2.dependencies or []) == [t1.id]

    await dispatch_due_tasks()
    dispatched = [d["metadata"]["source_task_id"] for d in captured.get("dispatches", [])]
    assert t2.id in dispatched


@pytest.mark.asyncio
async def test_queue_drained_published_on_drain_edge(
    _db, monkeypatch, tmp_path, duty_enabled  # noqa: ARG001
):
    """值守排空沿：上一轮有派发、本轮无派发 → 发布一次 queue_drained 战报。

    空闲轮（连续无派发）不得重复广播；发布前 in_progress>0 时跳过。
    """
    captured: dict = {}
    _patch_engine(monkeypatch, captured, tmp_path)

    from app.domain.tasks.runtime import dispatcher as dispatcher_module

    drained: list[dict] = []

    async def _fake_drained(**kwargs):
        drained.append(kwargs)

    monkeypatch.setattr(dispatcher_module, "publish_queue_drained", _fake_drained)

    t1 = await TaskQueueService.create_task(
        project_id=183, title="排空沿巡检", description="d", risk_level="T3"
    )

    # 第一轮：派发并运行（fake run 只 take）
    await dispatcher_module.dispatch_due_tasks()
    assert drained == []

    # 轮次收尾：任务推进到 completed（模拟 agent 正常收口）
    async with session_scope() as session:
        await session.execute(
            update(ProjectTask).where(ProjectTask.id == t1.id).values(status="completed")
        )

    # 第二轮：无派发 → 排空沿触发，发布一次战报
    await dispatcher_module.dispatch_due_tasks()
    assert len(drained) == 1
    assert drained[0]["completed"] >= 1

    # 第三轮：连续空闲 → 不重复广播
    await dispatcher_module.dispatch_due_tasks()
    assert len(drained) == 1
