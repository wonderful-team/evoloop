"""API routes for project duty (customer-service duty + business poll).

值守独立端点（v7 拆分，原混在 _profiles.settings / _listing 中）：
- GET  /projects/{id}/duty        读值守配置（enabled/channels/节奏/汇报目标）
- PUT  /projects/{id}/duty        更新值守配置（校验 + 启动/停止语义 + 失败回滚）
- GET  /projects/{id}/duty/status 读值守运行状态（参与开关 + 调度运行信息）

启停语义（§8.5.5/§8.5.6）：enabled=true → 校验并启动（失败回滚）；false → 停止切断。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import TokenDepOptional
from app.api.schemas.projects._duty import BusinessPollPrompt, DutyConfig
from app.core.project.utils import (
    get_project_path,
    read_project_json,
    write_project_json,
)
from app.infrastructure.database import session_scope
from app.models.scheduler import AutonomousTask

router = APIRouter(prefix="/{project_id}/duty", tags=["projects-duty"])


async def _load_duty(project_id: int) -> tuple[str, dict]:
    """读项目 project.json 的 customer_service_duty；无本地路径 404。"""
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    pj = read_project_json(path)
    return path, pj.get("customer_service_duty") or {}


@router.get("", response_model=DutyConfig)
async def get_project_duty(project_id: int, _token: TokenDepOptional = None):
    """读取项目值守配置（enabled/channels/business_poll_prompts）。

    轮巡间隔/业务巡检扫描间隔属全局值守设置，不在此返回。
    """
    _, duty = await _load_duty(project_id)
    return DutyConfig(
        enabled=duty.get("enabled"),
        channels=duty.get("channels"),
        business_poll_prompts=[
            BusinessPollPrompt(**p) for p in (duty.get("business_poll_prompts") or [])
        ],
    )


@router.put("", response_model=DutyConfig)
async def update_project_duty(
    project_id: int,
    req: DutyConfig,
    _token: TokenDepOptional = None,
):
    """更新项目值守配置（部分更新），并执行启动/停止语义。

    校验（422）：business_poll_prompts 为列表，每条含 id/prompt/next_run_at/
    interval_minutes/enabled。轮巡间隔/业务巡检扫描间隔属全局，不在项目 PUT 里。
    启停（§8.5.5/§8.5.6）：enabled=true → 校验全局/渠道条件并启动，
    失败回滚 enabled=false（400 + 失败原因）；false → 停止并协作式切断 Agent。
    """
    path, duty = await _load_duty(project_id)

    # 字段级校验（v6.3/v7）
    if req.business_poll_prompts is not None:
        for p in req.business_poll_prompts:
            iv = p.interval_minutes
            if isinstance(iv, bool) or not isinstance(iv, int) or not 1 <= iv <= 1440:
                raise HTTPException(
                    422,
                    detail={"message": f"任务 {p.id or 'unknown'} 的间隔须为 1~1440 分钟整数"},
                )
            if not p.prompt or not p.prompt.strip():
                raise HTTPException(
                    422,
                    detail={"message": f"任务 {p.id or 'unknown'} 内容不能为空"},
                )
            try:
                datetime.fromisoformat(p.next_run_at)
            except (ValueError, TypeError) as e:
                raise HTTPException(
                    422,
                    detail={"message": f"任务 {p.id or 'unknown'} 的 next_run_at 格式非法: {e}"},
                ) from None

    # 部分更新：只覆盖传入字段（保持原值不丢）
    update = req.model_dump(exclude_none=True)
    if update:
        merged = {**duty, **update}
        write_project_json(path, {"customer_service_duty": merged})

    # 启停语义（§8.5.5/§8.5.6）
    if req.enabled is not None:
        from app.core.channel.duty import provision

        if req.enabled:
            result = await provision.start_project(project_id)
            if not result.get("success"):
                # 失败即还原：enabled 回滚 false
                pj = read_project_json(path)
                cur_duty = pj.get("customer_service_duty") or {}
                cur_duty["enabled"] = False
                write_project_json(path, {"customer_service_duty": cur_duty})
                raise HTTPException(
                    400,
                    detail={
                        "message": "值守启动失败",
                        "errors": result.get("errors", []),
                    },
                )
        else:
            await provision.stop_project(project_id)

    _, saved = await _load_duty(project_id)
    return DutyConfig(
        enabled=saved.get("enabled"),
        channels=saved.get("channels"),
        business_poll_prompts=[
            BusinessPollPrompt(**p) for p in (saved.get("business_poll_prompts") or [])
        ],
    )


@router.get("/status")
async def get_project_duty_status(project_id: int, _token: TokenDepOptional = None):
    """读取项目值守运行状态（参与开关 + 调度运行信息）。

    返回：enabled / active / last_run_at / next_run_at / interval /
    business_poll_interval / business_last_run_at / business_next_run_at /
    last_failure / global_enabled。
    """
    from app.api.routes.projects._listing import _read_duty_status

    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    tasks: dict[str, Any] = {}
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(AutonomousTask).where(AutonomousTask.project_id == project_id)
            )
        ).scalars().all()
        for t in rows:
            kind = (t.params_template or {}).get("kind")
            if kind in ("wecom", "kf", "business_poll"):
                tasks[kind] = t
    return await _read_duty_status(project_id, path, tasks)
