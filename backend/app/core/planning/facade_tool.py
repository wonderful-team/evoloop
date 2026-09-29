"""Plan facade tool — single unified entry for structured planning (OpenCode `plan`
语义，保留 Evoloop 结构化计划资产，§10.2.2)。

把 create_plan / update_step_status 收敛为一次调用按 ``action`` 分发；
plan 保持 DB Plan/PlanStep 持久化 + 前端面板语义（Evoloop 独有资产，不改为
OpenCode 模式开关）。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

from sqlalchemy import delete, select

from app.core.engine.message.native_classes import RunnableConfig
from app.core.planning.constants import PlanStatus, PlanStepStatus
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
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
    action: Literal["create", "update_steps", "list"] = "create",
    title: str | None = None,
    steps: list[str | dict] | None = None,
    task_id: str | None = None,
    plan_id: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一计划管理（Agent 唯一工作清单，用户经前端面板只读查验）。

    Actions:
    - create:       新建/覆盖当前会话计划（title + steps 列表）。
    - update_steps: 批量更新多个步骤状态（一次调用可同时完成多项）。
    - list:         查看当前计划及各步骤状态。

    WHEN TO USE:
    - 长任务（>3 步）先用 plan create 落地结构化计划，再随推进批量 update_steps。
    - 每完成一步必须标 completed 并填 result（这步干了什么、结果如何）——
      这是用户在面板上查验"此前干了什么"的唯一数据来源；开始下一步前先标 in_progress。
    - 一次调用可混合多项：如一步 completed（带 result）+ 下一步 in_progress。
    - 前端计划面板会随调用实时刷新。
    - 收尾时发现非阻塞项（不影响本次任务的遗留问题/建议）不要自行记账，
      在收尾回复中列出并询问用户是否建为旁支任务（create_project_tasks）。

    Args:
        action: create / update_steps / list。
        title: create 时的计划标题。
        steps: create 时为步骤列表（每项字符串，或对象 {"title": "...", "description": "..."}，
               对象必须有 title 键）；update_steps 时为更新列表，每项
               {"step_id": "...", "status": "pending|in_progress|completed|failed", "result": "..."}——
               completed 必填 result；step_id 来自 create 返回表格或 list 输出。
        task_id: create 时关联的任务 ID。
        plan_id: update_steps / list 时的计划 ID（缺省自动解析当前会话最新计划）。
    """
    thread_id = config.get("configurable", {}).get("thread_id") if config else None

    def _normalize_step(step: str | dict) -> tuple[str, str | None]:
        if isinstance(step, str):
            title = step.strip()
            if not title:
                raise ValueError("steps 中存在空步骤")
            return title, None
        if not isinstance(step, dict):
            raise ValueError("steps 只支持字符串或对象")
        title = str(step.get("title") or step.get("name") or "").strip()
        if not title:
            raise ValueError("steps 对象缺少 title")
        description = step.get("description") or step.get("detail") or None
        if description is not None:
            description = str(description).strip() or None
        return title[:255], description

    outcome: str | tuple[str, dict] | None = None
    publish_kwargs: dict[str, Any] | None = None

    if action == "create":
        if not thread_id:
            return json.dumps({"error": "Missing thread_id in config"})
        if not title or not steps:
            return "Error: create 需要 title 和 steps。"
        try:
            normalized_steps = [_normalize_step(step) for step in steps]
        except ValueError as exc:
            return f"Error: {exc}"

        async with session_scope() as session:
            stmt = select(DBPlan).where(DBPlan.thread_id == thread_id)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                plan_id = existing.id
                existing.title = title
                if task_id:
                    existing.task_id = task_id
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
                        task_id=task_id,
                        title=title,
                        status=PlanStatus.ACTIVE.value,
                    )
                )
            db_steps = []
            for idx, (step_title, step_description) in enumerate(normalized_steps):
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
                        description=step_description,
                        status=step_status,
                        order=idx,
                    )
                )
                db_steps.append(
                    {"id": step_id, "title": step_title, "status": step_status}
                )

            lines = [f"### Plan Created: {title}", f"**Plan ID**: {plan_id}", ""]
            lines.append("| Step ID | Title | Status |")
            lines.append("| :--- | :--- | :--- |")
            for s in db_steps:
                lines.append(f"| `{s['id']}` | {s['title']} | {s['status']} |")
            lines.append(
                "\n*Tip: 用 plan(action='update_steps', steps=[{step_id, status, result}, ...]) "
                "批量更新步骤状态。*"
            )
            outcome = (
                "\n".join(lines),
                {
                    "id": plan_id,
                    "steps": db_steps,
                    "is_complete": False,
                },
            )
            publish_kwargs = {"thread_id": thread_id, "plan_id": plan_id}

    elif action == "update_steps":
        if not steps:
            return (
                "Error: update_steps 需要 steps 列表，每项 "
                '{"step_id": "...", "status": "pending|in_progress|completed|failed", "result": "..."}。'
            )
        updates: list[tuple[str, str, str]] = []
        for i, item in enumerate(steps):
            if not isinstance(item, dict):
                return f"Error: steps[{i}] 必须是对象（step_id/status/result）。"
            sid = str(item.get("step_id") or "").strip()
            st = str(item.get("status") or "").strip()
            res = str(item.get("result") or "").strip()
            if not sid or not st:
                return f"Error: steps[{i}] 缺少 step_id 或 status。"
            if st == "completed" and not res:
                return (
                    f"Error: steps[{i}]（{sid}）completed 必须填写 result"
                    "（这步做了什么、结果如何）。"
                )
            if len(res) > 500:
                res = res[:500]
            updates.append((sid, st, res))

        async with session_scope() as session:
            if not plan_id and thread_id:
                stmt = (
                    select(DBPlan)
                    .where(DBPlan.thread_id == thread_id)
                    .order_by(DBPlan.created_at.desc())
                )
                db_p = (await session.execute(stmt)).scalars().first()
                if db_p:
                    plan_id = db_p.id

            if not plan_id:
                return "Error: update_steps 需要 plan_id（或可自动解析的会话计划）。"

            stmt = (
                select(DBPlanStep)
                .where(DBPlanStep.plan_id == plan_id)
                .order_by(DBPlanStep.order)
            )
            existing = {s.id: s for s in (await session.execute(stmt)).scalars().all()}
            missing = [sid for sid, _, _ in updates if sid not in existing]
            if missing:
                return (
                    f"Error: 步骤不存在: {', '.join(missing)}。"
                    "请先用 plan(action='list') 查看有效 step_id。"
                )

            for sid, st, res in updates:
                step = existing[sid]
                step.status = st
                if res:
                    step.result = res

            lines = [f"### Steps Updated: {len(updates)}", ""]
            lines.append("| Step ID | Status | Result |")
            lines.append("| :--- | :--- | :--- |")
            for sid, st, res in updates:
                lines.append(f"| `{sid}` | {st} | {res or '-'} |")
            outcome = (
                "\n".join(lines),
                {
                    "action": "update_steps",
                    "plan_id": plan_id,
                    "updated": [
                        {"step_id": sid, "status": st} for sid, st, _ in updates
                    ],
                },
            )
            publish_kwargs = {
                "thread_id": thread_id,
                "plan_id": plan_id,
                "step_updates": [(sid, st) for sid, st, _ in updates],
            }

    elif action == "list":
        if not plan_id:
            return "Error: status 需要 plan_id。"
        async with session_scope() as session:
            db_plan = await session.get(DBPlan, plan_id)
            if not db_plan:
                return f"Error: Plan {plan_id} not found."
            stmt = (
                select(DBPlanStep)
                .where(DBPlanStep.plan_id == plan_id)
                .order_by(DBPlanStep.order)
            )
            db_steps = (await session.execute(stmt)).scalars().all()
            lines = [f"### Plan: {db_plan.title} (id={plan_id})", ""]
            lines.append("| Step ID | Title | Status |")
            lines.append("| :--- | :--- | :--- |")
            for s in db_steps:
                lines.append(f"| `{s.id}` | {s.title} | {s.status} |")
            outcome = "\n".join(lines), {"id": plan_id, "count": len(db_steps)}

    else:
        outcome = f"Error: unknown plan action '{action}'."

    if publish_kwargs:
        await _publish_plan_updated(**publish_kwargs)
    return outcome


async def _publish_plan_updated(
    thread_id: str | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    status: str | None = None,
    step_updates: list[tuple[str, str]] | None = None,
) -> None:
    try:
        from app.core.events import system_bus
        from app.core.planning.event import PlanUpdatedEvent

        if step_updates:
            for sid, st in step_updates:
                await system_bus.publish(
                    PlanUpdatedEvent(
                        thread_id=thread_id or "",
                        plan_id=plan_id or "",
                        step_id=sid,
                        status=st,
                    )
                )
        else:
            await system_bus.publish(
                PlanUpdatedEvent(
                    thread_id=thread_id or "",
                    plan_id=plan_id or "",
                    step_id=step_id,
                    status=status,
                )
            )
    except Exception as e:
        logger.warning(
            f"[plan] Failed to publish plan updated event: {e}", exc_info=True
        )
