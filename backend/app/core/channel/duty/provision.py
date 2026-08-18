"""值守供给（provision）— 值守的启动/停止/校验。

职责（§8.5.5/§8.5.6）：
- 前置校验：渠道全局启用、客户端/登录、项目凭据
- 启动：写项目配置 + upsert AutonomousTask（interval = 项目配置，缺省 60s）
- 停止：停用 AutonomousTask + 协作式切断正在运行的 Agent（§8.5.6）

值守是全局机制，项目是参与；停止分全局（托盘，停所有）/项目（项目页，停单个）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.core.channel.duty.config import (
    BUSINESS_POLL_INTERVAL,
    DUTY_INTERVAL,
    load_duty_config,
    load_global_duty_config,
    save_global_duty_config,
)
from app.core.channel.duty.scheduler import (
    KIND_BUSINESS_POLL,
    KIND_WECOM,
    task_is_duty,
)
from app.infrastructure.database import session_scope
from app.models.scheduler import AutonomousTask

logger = logging.getLogger(__name__)


# ── 前置校验 ──────────────────────────────────────────────

async def validate_global_duty() -> list[str]:
    """校验全局值守是否具备开启条件（渠道就绪检测），返回失败原因列表。

    校验项：企业微信客户端是否就绪（已安装 / 已登录 / 会话列表可读）。
    全局开启值守或启用渠道前调用，条件不满足则阻止开启。
    """
    errors: list[str] = []

    try:
        from app.core.channel.duty.wecom import common

        ready, reason = await common.check_wecom_ready()
        if not ready:
            errors.append(reason)
    except Exception as e:
        logger.warning("[wecom_provision] 全局就绪检测异常: %s", e)
        errors.append(f"企业微信就绪检测失败: {e}")

    return errors


async def validate_project_duty(project_id: int) -> list[str]:
    """校验某项目能否开启值守，返回失败原因列表（空 = 全部通过）。

    校验项：全局总开关、企微渠道已全局启用。不做 GUI 就绪检测——
    企微就绪已在"全局启用企微渠道"时校验过，项目开启依赖渠道已启用。

    注：企微凭据（corp_id/secret）是 API 接入的预留字段，GUI 值守
    （本地客户端登录）不需要，故此处不强制校验。
    """
    errors: list[str] = []

    global_cfg = load_global_duty_config()
    if not global_cfg.get("enabled"):
        errors.append("值守总开关未开启（请先在全局设置开启）")
    if "wecom" not in (global_cfg.get("channels") or []):
        errors.append("企微渠道未在全局启用")

    cfg = await load_duty_config(project_id)
    if not cfg:
        errors.append("项目无本地路径")

    return errors


# ── 启动 ──────────────────────────────────────────────────

async def start_project(project_id: int) -> dict:
    """开启某项目值守：校验 → 写配置 → upsert 企微/业务巡检两条 AutonomousTask。

    Returns: {"success": bool, "errors": list[str]}
    """
    errors = await validate_project_duty(project_id)
    if errors:
        return {"success": False, "errors": errors}

    await _enable_project_config(project_id)
    await _upsert_tasks(project_id)
    logger.info("[wecom_provision] 项目 %s 值守已启动", project_id)
    return {"success": True, "errors": []}


# ── 停止 ──────────────────────────────────────────────────

async def stop_project(project_id: int) -> dict:
    """停止某项目值守：停调度 + 协作式切断 Agent + 还原配置。"""
    await _deactivate_tasks(project_id)
    await _cancel_running_agents(project_id)
    await _disable_project_config(project_id)
    logger.info("[wecom_provision] 项目 %s 值守已停止", project_id)
    return {"success": True, "errors": []}


async def stop_global() -> dict:
    """停止全局值守（托盘）：写全局 enabled=false + 停所有启用项目的调度。

    只停调度 + 协作式切断 Agent，**保留各项目的 enabled（参与意愿）**——
    全局是总闸，项目 enabled 是分闸；全局重开后各项目按自己的 enabled 恢复
    （§8.5.6 ①，与 stop_project 不同：项目停止才写 enabled=false）。
    """
    global_cfg = load_global_duty_config()
    global_cfg["enabled"] = False
    save_global_duty_config(global_cfg)

    project_ids = await _active_duty_project_ids()
    for pid in project_ids:
        await _deactivate_tasks(pid)
        await _cancel_running_agents(pid)
    logger.info("[wecom_provision] 全局值守已停止")
    return {"success": True, "errors": []}


async def resume_global() -> dict:
    """全局重开（托盘/全局设置）：恢复所有仍保留 enabled 的项目的调度任务。

    全局是总闸：stop_global 只停调度、保留项目 enabled；全局重开后，
    各项目（project.json enabled=true 的）自动恢复轮巡，无需重新配置。
    """
    global_cfg = load_global_duty_config()
    global_cfg["enabled"] = True
    save_global_duty_config(global_cfg)

    # 遍历所有已登记的项目，恢复 project.json enabled=true 的调度
    from app.core.project.local_index import local_project_index
    from app.core.project.utils import get_workspace_root, read_project_json

    workspace_root = get_workspace_root()
    index = local_project_index.refresh(workspace_root) if workspace_root else {}
    resumed = 0
    for project_id, entry in index.items():
        try:
            pj = read_project_json(entry.path)
            duty = pj.get("customer_service_duty") or {}
            if duty.get("enabled"):
                await _upsert_tasks(int(project_id))
                resumed += 1
        except Exception as e:
            logger.warning("[wecom_provision] 恢复项目 %s 失败: %s", project_id, e)
    logger.info("[wecom_provision] 全局值守已开启，恢复 %d 个项目调度", resumed)
    return {"success": True, "errors": []}


# ── 内部实现 ──────────────────────────────────────────────

async def _enable_project_config(project_id: int) -> None:
    """写项目 project.json 的 customer_service_duty.enabled=true（保留企微参数）。"""
    from app.core.project.utils import (
        get_project_path,
        read_project_json,
        write_project_json,
    )

    path = await get_project_path(project_id)
    if not path:
        return
    pj = read_project_json(path)
    duty = pj.get("customer_service_duty") or {}
    duty["enabled"] = True
    write_project_json(path, {"customer_service_duty": duty})


async def _disable_project_config(project_id: int) -> None:
    """写项目 project.json 的 customer_service_duty.enabled=false（还原配置）。"""
    from app.core.project.utils import (
        get_project_path,
        read_project_json,
        write_project_json,
    )

    path = await get_project_path(project_id)
    if not path:
        return
    pj = read_project_json(path)
    duty = pj.get("customer_service_duty") or {}
    duty["enabled"] = False
    write_project_json(path, {"customer_service_duty": duty})


async def _upsert_tasks(project_id: int) -> None:
    """upsert 该项目的两条值守 AutonomousTask：企微轮巡 + 业务巡检扫描。"""
    cfg = await load_duty_config(project_id)
    wecom_interval = cfg.get("interval", DUTY_INTERVAL)
    business_interval = cfg.get(
        "business_poll_interval", BUSINESS_POLL_INTERVAL
    )
    await _upsert_task_by_kind(
        project_id,
        kind=KIND_WECOM,
        interval_seconds=wecom_interval,
    )
    await _upsert_task_by_kind(
        project_id,
        kind=KIND_BUSINESS_POLL,
        interval_seconds=business_interval * 60,
    )


async def _upsert_task_by_kind(
    project_id: int, kind: str, interval_seconds: int
) -> None:
    """upsert 某项目某一类值守 AutonomousTask。"""
    trigger_spec = f"interval:{interval_seconds}"
    async with session_scope() as session:
        stmt = select(AutonomousTask).where(AutonomousTask.project_id == project_id)
        tasks = (await session.execute(stmt)).scalars().all()
        task = next(
            (
                t
                for t in tasks
                if task_is_duty(t.params_template)
                and t.params_template.get("kind") == kind
            ),
            None,
        )
        if task is None:
            task = AutonomousTask(
                project_id=project_id,
                intent_description=f"客服值守-{kind}（项目 {project_id}，interval {interval_seconds}s）",
                skill_ids=[],
                trigger_type="interval",
                trigger_spec=trigger_spec,
                params_template={"duty_channel": "wecom_duty", "kind": kind},
                is_active=True,
                next_run_at=_next_run_at(),
            )
            session.add(task)
        else:
            task.skill_ids = []
            task.trigger_spec = trigger_spec
            task.is_active = True
            task.params_template = {"duty_channel": "wecom_duty", "kind": kind}
            task.next_run_at = _next_run_at()


async def _deactivate_tasks(project_id: int) -> None:
    """停用该项目的所有值守 AutonomousTask（阻止下轮触发）。"""
    async with session_scope() as session:
        stmt = select(AutonomousTask).where(AutonomousTask.project_id == project_id)
        tasks = (await session.execute(stmt)).scalars().all()
        for task in tasks:
            if task_is_duty(task.params_template):
                task.is_active = False


async def _active_duty_project_ids() -> list[int]:
    """返回当前至少有一个值守任务处于激活状态的项目 id 列表。"""
    async with session_scope() as session:
        stmt = select(AutonomousTask).where(
            AutonomousTask.is_active == True,  # noqa: E712
            AutonomousTask.project_id.isnot(None),
        )
        tasks = (await session.execute(stmt)).scalars().all()
        return list({
            t.project_id
            for t in tasks
            if t.project_id is not None and task_is_duty(t.params_template)
        })


async def _cancel_running_agents(project_id: int) -> None:
    """协作式切断该项目的值守 Agent（§8.5.6）。

    对值守 thread（duty_{project}_*）逐个走统一停止入口
    ``session_manager.stop_agent``（有活会话 → session.stop；无会话 →
    stop_run + cancel_worker 双兜底），与 web/voice/mobile 用户主动停止
    保持一致；随后轮询 AgentActivity.status 直到进入终态
    （done/cancelled/failed），确保"停止"真正完成才返回（供前端 HUD
    显示"已停止"）。
    """
    import asyncio

    from app.core.session.manager import session_manager

    thread_ids = await _duty_thread_ids(project_id)
    if not thread_ids:
        return

    for tid in thread_ids:
        try:
            await session_manager.stop_agent(tid, "duty_stop")
            logger.info("[wecom_provision] 已请求停止 Agent thread %s", tid)
        except Exception as e:
            logger.warning("[wecom_provision] 停止 thread %s 失败: %s", tid, e)

    # 等待所有值守 Agent 真正退出（最多 20s，协作式切断通常 <5s）。
    # Agent 停止终态：done / cancelled / failed / quota_exhausted（activity_state.end_run）。
    _TERMINAL = frozenset({"done", "cancelled", "failed", "quota_exhausted", "idle"})
    deadline = asyncio.get_event_loop().time() + 20.0
    for tid in list(thread_ids):
        while asyncio.get_event_loop().time() < deadline:
            status = await _thread_status(tid)
            if status in _TERMINAL:
                logger.info("[wecom_provision] Agent thread %s 已停止 (status=%s)", tid, status)
                break
            await asyncio.sleep(0.5)
        else:
            logger.warning("[wecom_provision] 等待 Agent thread %s 退出超时", tid)


async def _thread_status(thread_id: str) -> str:
    """读取 AgentActivity 当前 status（无记录返回 idle）。"""
    async with session_scope() as session:
        from app.models import AgentActivity

        activity = await session.get(AgentActivity, thread_id)
        return activity.status if activity else "idle"


async def _duty_thread_ids(project_id: int) -> list[str]:
    """查该项目的值守 thread_id（duty_{project}_%）。"""
    async with session_scope() as session:
        rows = await session.execute(
            text("SELECT DISTINCT thread_id FROM messages WHERE thread_id LIKE :prefix"),
            {"prefix": f"duty_{project_id}_%"},
        )
        return [r[0] for r in rows.all()]


def _next_run_at():
    return datetime.now(timezone.utc) + timedelta(seconds=10)
