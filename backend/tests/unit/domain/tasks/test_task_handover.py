"""Unit tests for in-session task handover across workflow tasks."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import update

from app.domain.tasks.runtime.dispatcher import _build_upstream_context
from app.domain.tasks.service import TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask


@pytest.mark.asyncio
async def test_has_downstream_dependents_dag_check(_db):
    """验证 DAG 拓扑判断：只有存在下游依赖的任务返回 True，叶子节点返回 False。"""
    t1_id = uuid.uuid4().hex
    t2_id = uuid.uuid4().hex
    t3_id = uuid.uuid4().hex
    t_std_id = uuid.uuid4().hex

    async with session_scope() as session:
        t1 = ProjectTask(
            id=t1_id,
            project_id=1,
            title="上游采集",
            status="in_progress",
            workflow_id="wf-test-dag-1",
            dependencies=[],
            last_result="采集完成",
        )
        t2 = ProjectTask(
            id=t2_id,
            project_id=1,
            title="中间处理",
            status="pending",
            workflow_id="wf-test-dag-1",
            dependencies=[t1_id],
            last_result="",
        )
        t3 = ProjectTask(
            id=t3_id,
            project_id=1,
            title="最终交付",
            status="pending",
            workflow_id="wf-test-dag-1",
            dependencies=[t2_id],
            last_result="",
        )
        t_standalone = ProjectTask(
            id=t_std_id,
            project_id=1,
            title="单发任务",
            status="in_progress",
            workflow_id=None,
            dependencies=[],
            last_result="单发完成",
        )
        session.add_all([t1, t2, t3, t_standalone])

    async with session_scope() as session:
        t1_loaded = await session.get(ProjectTask, t1_id)
        t2_loaded = await session.get(ProjectTask, t2_id)
        t3_loaded = await session.get(ProjectTask, t3_id)
        t_std_loaded = await session.get(ProjectTask, t_std_id)

        # 验证:
        # t1 有下游 t2 -> True
        assert await TaskQueueService.has_downstream_dependents(t1_loaded) is True
        # t2 有下游 t3 -> True
        assert await TaskQueueService.has_downstream_dependents(t2_loaded) is True
        # t3 是叶子节点，无下游 -> False
        assert await TaskQueueService.has_downstream_dependents(t3_loaded) is False
        # t_standalone 无工作流 -> False
        assert await TaskQueueService.has_downstream_dependents(t_std_loaded) is False


@pytest.mark.asyncio
async def test_submit_acceptance_triggers_handover_only_when_has_downstream(_db):
    """验证验收流转：仅当任务通过且有下游依赖时，才触发原会话交接生成；叶子任务跳过。"""
    up_id = uuid.uuid4().hex
    down_id = uuid.uuid4().hex

    from app.models.task_workflow import TaskWorkflow

    wf_id = uuid.uuid4().hex
    async with session_scope() as session:
        wf = TaskWorkflow(
            id=wf_id,
            project_id=1,
            title="测试流水线",
            goal="测试流水线目标",
            status="running",
        )
        t_up = ProjectTask(
            id=up_id,
            project_id=1,
            title="上游打分",
            status="waiting_acceptance",
            workflow_id=wf_id,
            dependencies=[],
            last_thread_id="wakeup_1_test_thread",
            last_result="完成打分 100 条",
        )
        t_down = ProjectTask(
            id=down_id,
            project_id=1,
            title="下游草稿",
            status="pending",
            workflow_id=wf_id,
            dependencies=[up_id],
            last_result="",
        )
        session.add_all([wf, t_up, t_down])

    mock_handover = AsyncMock(
        return_value="""### 交付清单
- **产物文件**：`.tmp/leads/tiered.json`
- **数据结构**：包含 `title`, `author`, `score`, `tier`
- **核心脚本**：`score_and_tier.py`
"""
    )

    with patch(
        "app.domain.tasks.handover.generate_in_session_handover", mock_handover
    ):
        # 1. 验收上游任务 t_up (有下游 t_down)
        res_up = await TaskQueueService.submit_acceptance(
            up_id, by="reviewer:auto", verdict="accepted"
        )
        assert res_up.status == "completed"
        # 必须触发交接生成
        assert mock_handover.call_count == 1

        # 检查落库数据
        async with session_scope() as session:
            db_up = await session.get(ProjectTask, up_id)
            assert "handover_summary" in (db_up.task_data or {})
            assert "### 交付清单" in db_up.task_data["handover_summary"]
            assert "### 交付交接清单" in db_up.last_result

    # 2. 验收下游任务 t_down (叶子任务，无下游)
    # 先更新状态到 waiting_acceptance
    async with session_scope() as session:
        await session.execute(
            update(ProjectTask)
            .where(ProjectTask.id == down_id)
            .values(
                status="waiting_acceptance",
                last_result="外联已生成",
                last_thread_id="wakeup_1_down_thread",
            )
        )

    mock_handover_leaf = AsyncMock()
    with patch(
        "app.domain.tasks.handover.generate_in_session_handover",
        mock_handover_leaf,
    ):
        res_down = await TaskQueueService.submit_acceptance(
            down_id, by="reviewer:auto", verdict="accepted"
        )
        assert res_down.status == "completed"
        # 叶子任务绝对不能调用交接生成！
        assert mock_handover_leaf.call_count == 0


@pytest.mark.asyncio
async def test_build_upstream_context_injects_full_handover_without_truncation(_db):
    """验证派发器上下文注入：完整保留 handover_summary，彻底移除 300 字符硬截断。"""
    up_id = uuid.uuid4().hex
    down_id = uuid.uuid4().hex

    long_handover = (
        "### #T-1 交付清单\n"
        "- **核心产物文件**：`/Users/test/Ruoyi-Cloud-Plus/data/leads/huge_report.json`\n"
        "- **数据结构说明**：每条包含 id, title, score, tier, contact_email, company_name, budget_hint\n"
        "- **处理脚本**：`python3 scripts/process_leads.py --input raw.json`\n"
        "- **下游建议**：请直接读取以上 JSON 文件，依据 tier == 'high' 过滤前 20 条，直接生成邮件，无需再次请求 API。\n"
        + ("详细注释信息说明 " * 30)  # 超过 300 字符
    )

    async with session_scope() as session:
        t_up = ProjectTask(
            id=up_id,
            project_id=1,
            title="上游处理",
            status="completed",
            task_no=1,
            last_result="基本完成",
            task_data={"handover_summary": long_handover},
        )
        t_down = ProjectTask(
            id=down_id,
            project_id=1,
            title="下游消费",
            status="pending",
            task_no=2,
            dependencies=[up_id],
        )
        session.add_all([t_up, t_down])

    async with session_scope() as session:
        t_down_loaded = await session.get(ProjectTask, down_id)
        context = await _build_upstream_context(t_down_loaded)

    # 验证注入成功
    assert "## 上游任务交付物与数据契约" in context
    assert "交付清单" in context
    assert "huge_report.json" in context
    assert "详细注释信息说明" in context
    # 确认未被 300 字符截断
    assert len(context) > 400
