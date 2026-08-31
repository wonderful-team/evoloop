"""Plan facade tool — single unified entry for structured planning (OpenCode `plan`
语义，保留 Evoloop 结构化计划资产，§10.2.2)。

把 create_plan / update_step_status 收敛为一次调用按 ``action`` 分发；
plan 保持 DB Plan/PlanStep 持久化 + 前端面板语义（Evoloop 独有资产，不改为
OpenCode 模式开关）。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal

from sqlalchemy import delete, select

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.domain.planning.constants import PlanStatus, PlanStepStatus
from app.infrastructure.database.sql.database import session_scope
from app.models.planning import Plan as DBPlan
from app.models.planning import PlanStep as DBPlanStep
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


@evoloop_tool(
    name="plan",
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.plan",
)
async def plan(
    action: Literal["create", "update_step", "status"] = "create",
    title: str | None = None,
    steps: list[str] | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    status: str | None = None,
    result: str = "",
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一计划管理（结构化执行计划）。

    Actions:
    - create:      新建/覆盖当前会话计划（title + steps 列表）。
    - update_step: 更新计划某一步状态（pending / in_progress / completed / failed）。
    - status:      查看当前计划及各步骤状态。

    WHEN TO USE:
    - 长任务（>3 步）先用 plan create 落地结构化计划，再逐步 update_step 推进。
    - 前端计划面板会随调用实时刷新。

    Args:
        action: create / update_step / status。
        title: create 时的计划标题。
        steps: create 时的步骤列表。
        plan_id: update_step / status 时的计划 ID。
        step_id: update_step 时的步骤 ID。
        status: update_step 时的新状态（pending/in_progress/completed/failed）。
        result: update_step 时的步骤结果描述。
    """
    thread_id = config.get("configurable", {}).get("thread_id") if config else None

    async with session_scope() as session:
        if action == "create":
            if not thread_id:
                return json.dumps({"error": "Missing thread_id in config"})
            if not title or not steps:
                return "Error: create 需要 title 和 steps。"
            stmt = select(DBPlan).where(DBPlan.thread_id == thread_id)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                plan_id = existing.id
                existing.title = title
                existing.status = PlanStatus.ACTIVE.value
                await session.execute(
                    delete(DBPlanStep).where(DBPlanStep.plan_id == plan_id)
                )
            else:
                plan_id = gen_uuid()
                session.add(
                    DBPlan(
                        id=plan_id,
                        thread_id=thread_id,
                        title=title,
                        status=PlanStatus.ACTIVE.value,
                    )
                )
            db_steps = []
            for idx, step_title in enumerate(steps):
                step_id = gen_uuid()
                step_status = (
                    PlanStepStatus.IN_PROGRESS.value
                    if idx == 0
                    else PlanStepStatus.PENDING.value
                )
                session.add(
                    DBPlanStep(
                        id=step_id,
                        plan_id=plan_id,
                        title=step_title,
                        status=step_status,
                        order=idx,
                    )
                )
                db_steps.append({"id": step_id, "title": step_title, "status": step_status})

            lines = [f"### Plan Created: {title}", f"**Plan ID**: {plan_id}", ""]
            lines.append("| Step ID | Title | Status |")
            lines.append("| :--- | :--- | :--- |")
            for s in db_steps:
                lines.append(f"| `{s['id']}` | {s['title']} | {s['status']} |")
            lines.append(
                "\n*Tip: 用 plan(action='update_step', ...) 更新每步状态。*"
            )
            await _publish_plan_updated(thread_id, plan_id)
            return "\n".join(lines), {
                "id": plan_id,
                "steps": db_steps,
                "is_complete": False,
            }

        if action == "update_step":
            if not plan_id or not step_id or not status:
                return "Error: update_step 需要 plan_id、step_id、status。"
            step = await session.get(DBPlanStep, step_id)
            if not step:
                return f"Error: Step {step_id} not found.", {"status": "error"}
            step.status = status
            if result:
                step.result = result
            await _publish_plan_updated(plan_id=plan_id, step_id=step_id, status=status)
            return (
                f"Successfully updated step {step_id} status to '{status}'.",
                {
                    "action": "update_step",
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "status": status,
                },
            )

        if action == "status":
            if not plan_id:
                return "Error: status 需要 plan_id。"
            db_plan = await session.get(DBPlan, plan_id)
            if not db_plan:
                return f"Error: Plan {plan_id} not found."
            stmt = select(DBPlanStep).where(DBPlanStep.plan_id == plan_id).order_by(DBPlanStep.order)
            db_steps = (await session.execute(stmt)).scalars().all()
            lines = [f"### Plan: {db_plan.title} (id={plan_id})", ""]
            lines.append("| Step ID | Title | Status |")
            lines.append("| :--- | :--- | :--- |")
            for s in db_steps:
                lines.append(f"| `{s.id}` | {s.title} | {s.status} |")
            return "\n".join(lines), {"id": plan_id, "count": len(db_steps)}

        return f"Error: unknown plan action '{action}'."


async def _publish_plan_updated(
    thread_id: str | None = None, plan_id: str | None = None, step_id: str | None = None, status: str | None = None
) -> None:
    try:
        from app.core.events import system_bus
        from app.domain.planning.event import PlanUpdatedEvent

        await system_bus.publish(
            PlanUpdatedEvent(
                thread_id=thread_id or "",
                plan_id=plan_id or "",
                step_id=step_id,
                status=status,
            )
        )
    except Exception as e:
        logger.warning(f"[plan] Failed to publish plan updated event: {e}", exc_info=True)
