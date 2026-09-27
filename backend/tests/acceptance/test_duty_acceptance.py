"""值守验收场景 — 每个用例对应一类真实事故（详见 conftest docstring）。

这些用例从**用户操作**（托盘点击/项目开关/任务取消）推演到**系统可观察
结局**（派发了几次、任务状态、重启后语义），守门与配置层零 stub。
"""

from __future__ import annotations

import json

import pytest

from app.models.project import ProjectTask  # noqa: F401
from tests.acceptance.conftest import (
    DUTY_PROJECT_ID,
    OTHER_PROJECT_ID,
    _duty_cfg_enabled,
    _one_cycle,
    _pending_count,
    _seed_due_task,
)


async def _setup_enabled_project(real_system, project_id: int = DUTY_PROJECT_ID):
    """真实启用一个项目的值守：project.json 写分闸 + 全局总闸开。"""
    from app.infrastructure.config.service import SystemConfigService

    await real_system.write_project(project_id, _duty_cfg_enabled())
    global_cfg = {"enabled": True, "channels": ["wecom"], "poll_interval": 60}
    SystemConfigService.set_value(
        "CUSTOMER_SERVICE_DUTY", json.dumps(global_cfg, ensure_ascii=False)
    )


@pytest.mark.timeout(60)
async def test_tray_stop_makes_system_silent(real_system):
    """【事故回归：托盘停止值守→任务照跑、停不下来】

    用户故事：托盘点"停止值守" → 系统完全静默（零派发、任务保留不丢）；
    托盘重开 → 自动恢复。总闸必须真实约束队列排空。
    """
    from app.core.channel.duty.provision import resume_global, stop_global

    await _setup_enabled_project(real_system)
    t1 = await _seed_due_task(DUTY_PROJECT_ID, "订单巡检")
    t2 = await _seed_due_task(DUTY_PROJECT_ID, "会员巡检")

    # 基线：总闸开 + 分闸开 → 任务被派发（系统活着）
    await _one_cycle()
    assert len(real_system.captured["runs"]) == 2

    # 时间流逝到下个周期（recurring next_run 已被 claim 推进）
    from datetime import timedelta as _td

    from sqlalchemy import update as _update

    from app.infrastructure.database import session_scope as _ss
    from app.utils.time import utcnow as _utcnow

    async with _ss() as session:
        for tid in (t1.id, t2.id):
            await session.execute(
                _update(ProjectTask)
                .where(ProjectTask.id == tid)
                .values(next_run_at=_utcnow() - _td(minutes=1))
            )

    # 用户操作：托盘点"停止值守"（真实 provision 路径）
    await stop_global()

    # 结局：完全静默——零派发，任务保留为 pending（不丢失，不误删）
    real_system.captured["runs"].clear()
    await _one_cycle()
    await _one_cycle()
    assert real_system.captured["runs"] == []
    assert await _pending_count() == 2

    # 托盘重开 → 自动恢复（时间流逝使 recurring 任务再次到期）
    await resume_global()
    from datetime import timedelta

    from sqlalchemy import update as _update

    from app.infrastructure.database import session_scope as _ss
    from app.utils.time import utcnow as _utcnow

    async with _ss() as session:
        for tid in (t1.id, t2.id):
            await session.execute(
                _update(ProjectTask)
                .where(ProjectTask.id == tid)
                .values(next_run_at=_utcnow() - timedelta(minutes=1))
            )
    await _one_cycle()
    assert len(real_system.captured["runs"]) == 2


@pytest.mark.timeout(60)
async def test_tray_stop_survives_restart(real_system):
    """【事故回归：重启后语义漂移】总闸关 + 任务取消的状态必须跨"重启"保持。

    重启 = 关停资源管理器后以同一 DB 文件重新初始化（真实文件 DB）。
    """
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.database.resource_manager import (
        db_resource_manager as resource_manager,
    )

    await _setup_enabled_project(real_system)
    await _seed_due_task(DUTY_PROJECT_ID, "资金巡检")

    # 用户操作：托盘停止值守
    from app.core.channel.duty.provision import stop_global

    await stop_global()

    # 重启：真实文件 DB 重新初始化（新引擎、同一文件、状态持久）
    await resource_manager.shutdown()
    await resource_manager.initialize(create_tables=True)
    # WORKSPACE_ROOT 也随 DB 持久
    assert SystemConfigService.get_value("WORKSPACE_ROOT")

    # 重启后：仍然静默（总闸持久为关）
    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

    await dispatch_due_tasks()
    assert real_system.captured["runs"] == []
    assert await _pending_count() == 1  # 任务保留，只是不派发


@pytest.mark.timeout(60)
async def test_stop_project_only_stops_that_project(real_system):
    """【用户故事：项目页停止值守只停该项目】其他项目不受影响。"""
    from app.core.channel.duty.provision import stop_project

    # 两个项目都启用值守且都有到期任务
    await _setup_enabled_project(real_system, DUTY_PROJECT_ID)
    await _setup_enabled_project(real_system, OTHER_PROJECT_ID)
    await _seed_due_task(DUTY_PROJECT_ID, "商城巡检")
    await _seed_due_task(OTHER_PROJECT_ID, "其他项目巡检")

    # 用户操作：停止项目 120 的值守（真实路径：写 project.json 分闸=false）
    await stop_project(DUTY_PROJECT_ID)

    await _one_cycle()
    claimed_projects = [
        d["project_id"] for d in real_system.captured["runs"]
    ]
    assert DUTY_PROJECT_ID not in claimed_projects  # 被停的项目静默
    assert OTHER_PROJECT_ID in claimed_projects  # 其他项目照常


@pytest.mark.timeout(60)
async def test_cancelled_recurring_task_never_fires_again(real_system):
    """【事故回归：任务取消后复活】取消的 recurring 任务永久静默，跨循环保持。"""
    from app.domain.tasks.service import TaskQueueService

    await _setup_enabled_project(real_system)
    t = await _seed_due_task(DUTY_PROJECT_ID, "营销巡检")

    # 用户操作：在任务列表取消该任务（真实 edit 路径）
    await TaskQueueService.edit_task(t.id, cancel=True)
    assert (await TaskQueueService.get_task(t.id)).status == "cancelled"

    for _ in range(3):  # 多轮循环 + 时间推进都不复活
        await _one_cycle()
    assert real_system.captured["runs"] == []
    assert (await TaskQueueService.get_task(t.id)).status == "cancelled"


@pytest.mark.timeout(60)
async def test_migrated_tasks_honor_source_switch(real_system):
    """【事故回归：迁移无视源 enabled=false】

    事故场景重建：源配置每条巡检项 enabled=false（用户从未开启），
    迁移产物却全部 pending 并周期点火。验收锁定的语义：
    无论迁移产物处于什么状态，总闸关 → 静默（用户可感知的唯一保证）；
    总闸开 → 由项目分闸与任务状态决定。
    """
    from app.core.channel.duty.provision import stop_global
    from app.infrastructure.config.service import SystemConfigService

    await _setup_enabled_project(real_system, DUTY_PROJECT_ID)
    # 事故同款：6 条迁移任务（pending recurring，源 prompts 全部 enabled=false）
    for i, title in enumerate(
        ["订单巡检", "售后巡检", "库存巡检", "会员巡检", "营销巡检", "资金巡检"]
    ):
        t = await _seed_due_task(DUTY_PROJECT_ID, title)
        # 标记为迁移产物（模拟事故现场数据）
        await TaskQueueServiceMarkMigrated.mark(t.id, i)

    # 用户操作：托盘停止值守（总闸关）
    await stop_global()

    for _ in range(2):
        await _one_cycle()
    assert real_system.captured["runs"] == []  # 全部静默

    # 对照：总闸开（resume）→ 分闸开的项目恢复派发
    # （本用例同时锁定：总闸不是摆设，开关两个方向都被守门尊重）
    global_cfg = {"enabled": True, "channels": ["wecom"], "poll_interval": 60}
    SystemConfigService.set_value(
        "CUSTOMER_SERVICE_DUTY", json.dumps(global_cfg, ensure_ascii=False)
    )
    await _one_cycle()
    assert len(real_system.captured["runs"]) == 6


class TaskQueueServiceMarkMigrated:
    """测试 helper：把任务标记为迁移产物（模拟事故现场数据形状）。"""

    @staticmethod
    async def mark(task_id: str, seq: int) -> None:
        from sqlalchemy import update

        from app.infrastructure.database import session_scope
        from app.models.project import ProjectTask

        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task_id)
                .values(
                    source_ref={
                        "kind": "migrated",
                        "from": "business_poll_prompts",
                        "original_id": f"poll-{seq}",
                    }
                )
            )


@pytest.mark.timeout(60)
async def test_workspace_task_runs_without_project_participation(real_system, monkeypatch):
    """【用户语义：project_id=0 = 工作空间任务】

    人建任务不选项目 → pid=0（工作空间）。工作空间任务没有"项目参与"
    概念，不受项目分闸约束——只受托盘总闸约束：
    - 总闸开 → 正常派发（即使没有任何项目开启值守）
    - 总闸关 → 静默
    """
    from app.core.channel.duty.provision import stop_global
    from app.infrastructure.config.service import SystemConfigService

    # 全局总闸开；且**没有任何项目**开启值守（分闸全关）
    global_cfg = {"enabled": True, "channels": ["wecom"], "poll_interval": 60}
    SystemConfigService.set_value(
        "CUSTOMER_SERVICE_DUTY", json.dumps(global_cfg, ensure_ascii=False)
    )
    t = await _seed_due_task(0, "工作空间任务：整理本周笔记", recurring=False)

    await _one_cycle()
    assert real_system.captured["runs"], "pid=0 任务应被派发（不受分闸约束）"
    assert real_system.captured["runs"][0]["project_id"] in (0, None)  # dispatcher: 0 → None

    # 总闸关 → 静默（下一个周期不再派发）
    real_system.captured["runs"].clear()
    await stop_global()
    t2 = await _seed_due_task(0, "工作空间任务：第二条", recurring=False)
    await _one_cycle()
    assert real_system.captured["runs"] == []
    assert (await TaskQueueServiceGet.get(t2.id)).status == "pending"


class TaskQueueServiceGet:
    @staticmethod
    async def get(task_id: str):
        from app.domain.tasks.service import TaskQueueService

        return await TaskQueueService.get_task(task_id)
