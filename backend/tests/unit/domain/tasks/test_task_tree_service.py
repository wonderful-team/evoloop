"""Test parent/subtask tree hierarchy and DAG dependencies in TaskQueueService and tasks tool."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.context.manager import ContextManager
from app.domain.tasks.service import TaskQueueService
from app.domain.tasks.tools.tasks_tool import tasks as tasks_tool


@pytest.mark.asyncio
async def test_parent_subtask_creation_and_root_only_filtering(_db):
    project_id = 999
    # 1. 创建一个根任务
    root_task = await TaskQueueService.create_task(
        project_id=project_id,
        title="主干目标：电商双十一营销",
        description="根任务",
    )
    assert root_task.parent_id is None

    # 2. 创建两个子任务挂在 root_task 下
    sub1 = await TaskQueueService.create_task(
        project_id=project_id,
        title="步骤1：选品与竞品分析",
        parent_id=root_task.id,
        dependencies=[],
        risk_level="T4",
    )
    assert sub1.parent_id == root_task.id
    # 拆解不变量：带 parent_id 创建自动补父依赖（画布连线/派发顺序权威）
    assert (sub1.dependencies or []) == [root_task.id]

    sub2 = await TaskQueueService.create_task(
        project_id=project_id,
        title="步骤2：生成营销文案与视觉素材",
        parent_id=root_task.id,
        dependencies=[sub1.id],
    )
    assert sub2.parent_id == root_task.id
    # 显式依赖保序，父依赖幂等回填不重复
    assert (sub2.dependencies or []) == [sub1.id, root_task.id]

    # 3. 根任务过滤测试 (root_only=True)
    roots = await TaskQueueService.list_tasks(project_id=project_id, root_only=True)
    root_ids = [r.id for r in roots]
    assert root_task.id in root_ids
    assert sub1.id not in root_ids
    assert sub2.id not in root_ids

    # 4. 全量查询 (root_only=False)
    all_tasks = await TaskQueueService.list_tasks(project_id=project_id, root_only=False)
    all_ids = [t.id for t in all_tasks]
    assert root_task.id in all_ids
    assert sub1.id in all_ids
    assert sub2.id in all_ids

    # 5. 子任务统计测试 (get_subtasks_counts)
    counts = await TaskQueueService.get_subtasks_counts([root_task.id])
    assert root_task.id in counts
    assert counts[root_task.id]["total"] == 2
    assert counts[root_task.id]["completed"] == 0

    # 完成一个子任务 (in_progress -> self_checked -> completed)
    await TaskQueueService.take_task(sub1.id, "th-sub1")
    await TaskQueueService.advance_task(sub1.id, "self_checked", by="agent", result="完成选品")

    counts_after = await TaskQueueService.get_subtasks_counts([root_task.id])
    assert counts_after[root_task.id]["total"] == 2
    assert counts_after[root_task.id]["completed"] == 1


@pytest.mark.asyncio
async def test_tasks_tool_supports_parent_and_dependencies(_db, monkeypatch):
    project_id = 998
    monkeypatch.setattr(
        ContextManager,
        "current",
        lambda: SimpleNamespace(project_id=project_id, current_task_id=None),
    )

    # 1. 通过工具创建根任务
    res_raw = await tasks_tool(action="create", title="Agent 根规划任务")
    res = json.loads(res_raw)
    assert res["success"] is True
    root_id = res["id"]
    assert res.get("parent_id") is None

    # 2. 通过工具创建子任务
    sub_raw = await tasks_tool(
        action="create",
        title="Agent 子规划步骤 1",
        parent_id=root_id,
        dependencies=[root_id],
    )
    sub_res = json.loads(sub_raw)
    assert sub_res["success"] is True
    assert sub_res["parent_id"] == root_id

    # 3. 通过工具列出任务 (root_only=True)
    list_root_raw = await tasks_tool(action="list", root_only=True)
    list_root = json.loads(list_root_raw)
    assert any(t["id"] == root_id for t in list_root["items"])
    assert not any(t["id"] == sub_res["id"] for t in list_root["items"])

    # 4. 通过工具列出任务 (root_only=False)
    list_all_raw = await tasks_tool(action="list", root_only=False)
    list_all = json.loads(list_all_raw)
    assert any(t["id"] == root_id for t in list_all["items"])
    assert any(t["id"] == sub_res["id"] for t in list_all["items"])
