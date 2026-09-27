"""WorkflowService 单测（阶段九收敛后形态）。

- growth 流水线：create_growth_workflow 走通用轮次机制（模板+confirm+spawn），
  阶段任务=普通 pending 任务（无 task_data 特权标记、无专属执行器）；
- 通用轮次机制：聚合状态刷新（refresh_status 幂等/取消保护）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.tasks.service import TaskQueueService
from app.domain.tasks.workflows import WorkflowError, WorkflowService


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_growth_workflow_spawns_five_stage_dag(_db):
    workflow, tasks = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="测试上新",
        goal="验证文本增长闭环",
        inputs={"category": "宠物"},
    )

    assert workflow.status == "running"
    assert workflow.round_no == 1
    assert [t.title for t in tasks] == [
        "市场调研",
        "机会发现",
        "选品评估",
        "商品理解",
        "上架文案",
    ]
    # 阶段任务=普通任务：无 task_data 特权标记，阶段 key 在 source_ref
    assert all(not (t.task_data or {}).get("workflow_runtime") for t in tasks)
    assert [t.source_ref["stage"] for t in tasks] == [
        "market_research",
        "product_opportunity_scan",
        "selection_dossier",
        "product_brief_builder",
        "listing_copy_generator",
    ]
    assert all(t.workflow_round == 1 for t in tasks)
    assert all(t.category == "growth_workflow" for t in tasks)
    # 依赖链为同轮真实任务 id（deps 接线正确）
    assert tasks[0].dependencies == []
    assert tasks[1].dependencies == [tasks[0].id]
    # 阶段描述承载角色 prompt + 产出契约 + tasks 工具执行协议
    assert "json.loads" in tasks[0].description
    assert "update_status" in tasks[0].description

    due = await TaskQueueService.claim_due_tasks()
    assert [task.id for task in due] == [tasks[0].id]


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_list_workflows_returns_project_history(_db):
    first, _ = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="第一批上新",
        goal="验证工作流历史",
    )
    second, _ = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="第二批上新",
        goal="验证工作流历史排序",
    )
    await WorkflowService.create_growth_workflow(
        project_id=2,
        title="其他项目",
        goal="不应出现在项目 1 的历史里",
    )

    workflows = await WorkflowService.list_workflows(1)

    assert {workflow.id for workflow in workflows} == {first.id, second.id}
    assert all(workflow.project_id == 1 for workflow in workflows)


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_refresh_status_skips_unchanged_status_event(_db, monkeypatch):
    publish_event = AsyncMock()
    monkeypatch.setattr(
        "app.domain.tasks.workflows.publish_workflow_event",
        publish_event,
    )
    workflow, tasks = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="测试事件去重",
        goal="验证 running 状态不重复广播",
    )
    thread = f"agent_thread_{tasks[0].id[:8]}"
    await TaskQueueService.take_task(tasks[0].id, thread)
    await TaskQueueService.advance_task(
        tasks[0].id,
        "self_checked",
        result="市场扫描完成",
        self_check={"verdict": "pass", "checks": [], "deviations": []},
        thread_id=thread,
    )
    await WorkflowService.refresh_status(workflow.id)

    events = [call.kwargs.get("event") for call in publish_event.await_args_list]
    # advance 内嵌 refresh 已把 running 维持；显式 refresh 不重复广播
    assert "workflow_status_changed" not in events


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_completed_stage_releases_dependency(_db):
    workflow, tasks = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="测试上新",
        goal="验证依赖放行",
    )
    thread = f"agent_thread_{tasks[0].id[:8]}"
    await TaskQueueService.take_task(tasks[0].id, thread)
    await TaskQueueService.advance_task(
        tasks[0].id,
        "self_checked",
        result="市场扫描完成",
        self_check={"verdict": "pass", "checks": [], "deviations": []},
        thread_id=thread,
    )

    due = await TaskQueueService.claim_due_tasks()
    assert [task.id for task in due] == [tasks[1].id]


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_growth_stage_completes_workflow(_db):
    """全阶段终态 → advance 内嵌 refresh 把 workflow 聚合为 completed。

    文案阶段是 T2 → self_checked 落 waiting_acceptance（等人拍板，
    与旧路径同语义）；用户验收后才收口。
    """
    workflow, tasks = await WorkflowService.create_growth_workflow(
        project_id=1,
        title="测试收口",
        goal="验证聚合联动",
    )
    waiting_task_id = ""
    for stage in tasks:
        thread = f"agent_thread_{stage.id[:8]}"
        await TaskQueueService.take_task(stage.id, thread)
        await TaskQueueService.advance_task(
            stage.id,
            "self_checked",
            result="阶段完成",
            self_check={"verdict": "pass", "checks": [], "deviations": []},
            thread_id=thread,
        )
        fresh = await TaskQueueService.get_task(stage.id)
        if fresh is not None and fresh.status == "waiting_acceptance":
            waiting_task_id = stage.id
    mid = await WorkflowService.get_workflow(workflow.id)
    assert mid.status == "waiting_acceptance"  # T2 阶段闸门正确聚合
    await TaskQueueService.submit_acceptance(
        waiting_task_id, by="user", verdict="accepted"
    )
    refreshed = await WorkflowService.get_workflow(workflow.id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("duty_enabled")
async def test_growth_requires_title_and_goal(_db):
    with pytest.raises(WorkflowError, match="title"):
        await WorkflowService.create_growth_workflow(
            project_id=1, title="  ", goal="g"
        )
    with pytest.raises(WorkflowError, match="goal"):
        await WorkflowService.create_growth_workflow(
            project_id=1, title="t", goal=" "
        )
