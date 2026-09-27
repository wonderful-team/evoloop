"""值守验收测试 — 从用户操作（托盘/项目开关）推演到系统可观察结局。

与 tests/unit 的本质区别：
- **零 stub 守门/配置层**：load_duty_config / load_global_duty_config /
  SystemConfigService / read-write_project_json / claim_due_tasks /
  provision.stop_global / get_project_path 全部走真实代码与真实状态
  （真实文件 DB + 真实 workspace 目录）；
- 唯一 stub：Agent 执行体（run_agent_background / dispatch_agent_run 的
  LLM/MCP 边界）；
- 断言的是**用户可观察结局**：派发了没有、日志级停止是否真的静默、
  任务取消后是否复活、重启后语义是否保持。

场景对应的历史事故：
- 托盘停止值守 → 任务照跑（总闸不在守门逻辑里）→ test_tray_stop_makes_system_silent
- migrated 任务无视源 enabled=false → test_migrated_tasks_honor_source_switch
- 任务取消后复活 / 重启后语义漂移 → test_cancelled_recurring_task_*
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings

DUTY_PROJECT_ID = 120
OTHER_PROJECT_ID = 121


async def _write_project_workspace(workspace: Path, project_id: int, duty_cfg: dict | None):
    """真实建项目目录 + project.json（与生产格式一致，经真实读取路径生效）。"""
    proj_dir = workspace / f"proj-{project_id}"
    (proj_dir / ".evoloop").mkdir(parents=True, exist_ok=True)
    meta = {"project_id": project_id, "name": f"project-{project_id}"}
    if duty_cfg is not None:
        meta["customer_service_duty"] = duty_cfg
    (proj_dir / ".evoloop" / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    return proj_dir


def _duty_cfg_enabled() -> dict:
    """与事故现场一致的值守配置（项目分闸开 + callback 渠道）。"""
    return {
        "enabled": True,
        "channels": {
            "callback": {
                "enabled": True,
                "mcp_server": "capability-matrix",
                "site_id": 1,
            }
        },
        "interval": 60,
    }


@pytest.fixture
async def real_system(tmp_path: Path, monkeypatch):
    """真实文件 DB + 真实配置存储 + 真实 workspace 解析（零守门 stub）。

    本 fixture 替代 unit 层的 in-memory patch：守门、配置读取、provision
    全部走生产代码路径。唯一保留的 stub 是引擎执行体（见 engine_stub）。
    """
    db_file = tmp_path / "backend.db"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)

    monkeypatch.setattr(settings, "SQLITE_PATH", str(db_file))
    from app.infrastructure.config.service import SystemConfigService

    # WORKSPACE_ROOT 走真实存储（SystemConfigService → DB），供 get_project_path 解析
    # （此时 DB 未建，set_value 需在 initialize 之后；先暂存，init 后写入）
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True)
    SystemConfigService.set_value("WORKSPACE_ROOT", str(workspace))

    # 引擎执行体 stub（LLM/MCP 边界）——记录"派发即执行"
    from app.core.engine.dispatch import DispatchStatus

    captured: dict = {"runs": []}

    async def _fake_dispatch(**kwargs):
        captured["runs"].append(kwargs)
        return SimpleNamespace(
            status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
        )

    async def _fake_run_agent_background(thread_id, _inputs):
        from app.domain.tasks.service import TaskQueueService

        last = captured["runs"][-1]
        task_id = last["metadata"]["source_task_id"]
        await TaskQueueService.take_task(task_id, thread_id)
        # 模拟 Agent 完成任务：recurring 经 self_checked 回队 pending
        # （真实流转见 service.advance_task——桩保真到状态推进，否则
        # 任务卡 in_progress，后续周期语义失真）
        await TaskQueueService.advance_task(
            task_id, "self_checked", result="done (stub)"
        )

    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
    )
    monkeypatch.setattr(
        "app.core.engine.agent.run_agent_background", _fake_run_agent_background
    )

    yield SimpleNamespace(
        workspace=workspace,
        db_file=db_file,
        captured=captured,
        write_project=lambda pid, cfg: _write_project_workspace(
            workspace, pid, cfg
        ),
    )

    await db_resource_manager.shutdown()


async def _seed_due_task(project_id: int, title: str, *, recurring: bool = True):
    from datetime import timedelta
    from sqlalchemy import update
    from app.domain.tasks.service import TaskQueueService
    from app.infrastructure.database import session_scope
    from app.models.project import ProjectTask
    from app.utils.time import utcnow

    t = await TaskQueueService.create_task(
        project_id=project_id,
        title=title,
        description=f"{title} 的巡检指令",
        type="recurring" if recurring else "once",
        source="user",
        trigger_spec="interval:1800" if recurring else None,
        due_at=None,
    )
    if recurring:
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == t.id)
                .values(next_run_at=utcnow() - timedelta(seconds=1))
            )
        t.next_run_at = utcnow() - timedelta(seconds=1)
    return t


async def _one_cycle():
    """跑一轮完整值守循环（真实组件：dispatch + tick）。"""
    from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks
    from app.infrastructure.scheduler.service import SchedulerService

    await dispatch_due_tasks()
    await SchedulerService.tick()


async def _pending_count() -> int:
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.project import ProjectTask

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(ProjectTask).where(ProjectTask.status == "pending")
                )
            )
            .scalars()
            .all()
        )
        return len(rows)
