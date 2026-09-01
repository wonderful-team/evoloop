"""Schedule facade tool — single unified entry for autonomous scheduled tasks.

把创建周期任务 / 查看自主任务 收敛为单一 ``schedule`` 工具按 ``action`` 分发：
- create: 委派一个周期性执行的任务给自主调度器——按 ``macro_id``（或宏名）关联一个宏，
          到点直接由引擎执行该宏（不强制设备池、不经 agent）。
- list:   列出由 Agent 管理的所有自主任务（可按项目过滤）。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import select

from app.core.execution.system_tools_formatter import SystemToolsFormatter
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.models.scheduler import AutonomousTask
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(
    name="schedule",
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.schedule",
)
async def schedule(
    action: Literal["create", "list"] = "list",
    intent: str | None = None,
    trigger: str | None = None,
    macro_id: int | None = None,
    macro_name: str | None = None,
    params: dict[str, Any] | None = None,
    project_id: int | None = None,
) -> str:
    """统一定时任务（自主调度）入口。

    Actions:
    - create: 委派一个周期性执行的任务给自主调度器——关联一个已存在的宏，到点由引擎执行。
    - list:   列出由 Agent 管理的所有自主任务（可按 project_id 过滤）。

    WHEN TO USE:
    - 用户说"每天自动做 XX / 定时执行 / 周期性检查 XX" → create（关联一个已验证宏周期执行）。
    - 想查看已有哪些自主任务在跑 → list。
    - 注意：create 需要宏（macro_id 或 macro_name 必填其一），宏必须先 verified 且 active。

    Args:
        action: 执行的动作（create / list）。
        intent: create 时必填，目标的高层描述（如"每天抓取闲鱼新发商品"）。
        trigger: create 时必填，Cron 表达式（如 "0 12 * * *"）或间隔规格（如 "interval:3600"）。
        macro_id: create 时必填（与 macro_name 二选一），要执行的宏 ID。
        macro_name: create 时可选，宏名（提供时按项目解析出宏 ID）。
        params: create 时传给宏的执行参数（如 {{keyword}} 之类的占位符值）。
        project_id: 可选项目上下文 ID（create 归属 / list 过滤）。
    """
    if action == "list":
        return await _schedule_list(project_id=project_id)

    return await _schedule_create(
        intent=intent,
        trigger=trigger,
        macro_id=macro_id,
        macro_name=macro_name,
        params=params,
        project_id=project_id,
    )


async def _schedule_create(
    intent: str | None,
    trigger: str | None,
    macro_id: int | None,
    macro_name: str | None,
    params: dict[str, Any] | None,
    project_id: int | None,
) -> str:
    """委派一个周期性执行的任务给自主调度器（关联宏）。"""
    if not intent or not trigger:
        return ControllerResponse.error(
            "schedule create 需要 intent、trigger",
            note="intent=任务描述；trigger=Cron 或 interval:秒。",
        )
    if macro_id is None and not macro_name:
        return ControllerResponse.error(
            "schedule create 需要 macro_id 或 macro_name",
            note="关联一个已验证宏，到点自动执行。可用 macro list 查看可用宏。",
        )

    try:
        from app.infrastructure.scheduler.service import SchedulerService

        resolved_macro_id = macro_id
        if resolved_macro_id is None:
            from app.core.learning.macro import find_macro_by_name

            macro = await find_macro_by_name(macro_name, project_id=project_id)
            if macro is None:
                return ControllerResponse.not_found(macro_name, item_type="Macro")
            resolved_macro_id = macro.id

        task_id = await SchedulerService.register_task(
            intent_description=intent,
            macro_id=resolved_macro_id,
            trigger_spec=trigger,
            params=params,
            project_id=project_id,
        )

        return ControllerResponse.success(
            f"已委派周期任务：{intent}",
            details=f"Task ID: {task_id}",
            note=f"Trigger: {trigger}",
        )
    except Exception as e:
        logger.exception("Error in schedule create: %s", e)
        return ControllerResponse.error("Failed to delegate intent", details=str(e))


async def _schedule_list(project_id: int | None) -> str:
    """列出由 Agent 管理的所有自主任务。"""
    try:
        async with session_scope() as session:
            stmt = select(AutonomousTask)
            if project_id is not None:
                stmt = stmt.where(AutonomousTask.project_id == project_id)

            result = await session.execute(stmt)
            tasks = result.scalars().all()

            if not tasks:
                return "No autonomous tasks found.", {"count": 0}

            try:
                return SystemToolsFormatter.autonomous_tasks(tasks), {"count": len(tasks)}
            except Exception as e:
                logger.exception("Failed to render task list: %s", e)
                return f"Found {len(tasks)} tasks.", {"count": len(tasks)}
    except Exception as e:
        logger.exception("Error in schedule list: %s", e)
        return f"Error: Failed to list tasks. {str(e)}"
