import json
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import func, select

from app.infrastructure.database import session_scope
from app.models.scheduler import AutonomousTask

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Main service for orchestrating autonomous tasks and periodic agent delegations.
    """

    @staticmethod
    async def tick():
        """
        Poll for due tasks and dispatch them to the background worker.

        调用方为 API 进程 lifespan 的 asyncio 调度循环（main.py，每 60s）。
        启动即先 tick：next_run_at <= now 的扫描语义天然覆盖离线补跑
        （进程死亡期间到期的任务，重启后首轮 tick 全部命中，无需独立 misfire 机制）。
        注：历史上此处的 "Huey periodic" 描述为过时注释，Huey 与 tick 触发无关。
        """
        # 存量宏类行一次性幂等迁移（AutonomousTask 收缩为纯定时器后宏走队列）
        await SchedulerService.convert_legacy_macro_rows()

        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            # 1. Catch active & due tasks (fetch only IDs)
            # 注意：不能写 `not AutonomousTask.is_dead_letter`——对 SQLAlchemy
            # Column 用 Python `not` 会在构造语句时就求值为常量 False，导致
            # 查询恒空、所有 AutonomousTask 永不派发。必须用 is_(False) /
            # coalesce 生成 SQL 条件。
            stmt = select(AutonomousTask.id).where(
                AutonomousTask.is_active,
                func.coalesce(AutonomousTask.is_dead_letter, False).is_(False),
                AutonomousTask.next_run_at <= now,
            )
            result = await session.execute(stmt)
            due_task_ids = result.scalars().all()

        if not due_task_ids:
            return

        logger.info(f"[Scheduler] Found {len(due_task_ids)} due tasks.")

        for task_id in due_task_ids:
            try:
                await SchedulerService.dispatch_task(task_id)
            except Exception as e:
                logger.exception(f"[Scheduler] Failed to dispatch task {task_id}: {e}")

        # AutonomousTask 已收缩为纯定时器：本 tick 只负责值守轮巡触发
        # （wecom GUI / mcp_message poll 兜底，机械采集、进程内直接执行）。
        # 工作项（周期委派/外部消息/人建/Agent 建）一律走 ProjectTask 队列，
        # 由 duty supervisor 单 drainer 排空。

    @staticmethod
    async def convert_legacy_macro_rows() -> int:
        """存量宏类 AutonomousTask 行 → recurring ProjectTask（一次性幂等迁移）。

        AutonomousTask 收缩为纯定时器后，定时宏执行改为工作项语义：
        supervisor 排空 → Agent 经 macro 工具执行（自带宏失败的自适应处理）。
        转换后原行墓碑化（is_active=False）；幂等：重复执行零转换。
        """
        from app.domain.tasks.service import TaskQueueService

        async with session_scope() as session:
            stmt = select(AutonomousTask).where(
                AutonomousTask.macro_id.isnot(None),
                AutonomousTask.is_active.is_(True),
            )
            rows = (await session.execute(stmt)).scalars().all()

        converted = 0
        for task in rows:
            params = dict(task.params_template or {})
            param_text = (
                json.dumps(params, ensure_ascii=False) if params else "无"
            )
            intent = task.intent_description or f"定时执行宏 #{task.macro_id}"
            await TaskQueueService.create_task(
                project_id=task.project_id or 0,
                title=intent,
                description=(
                    f"{intent}\n\n"
                    f"[legacy-migrated] 到点执行宏 #{task.macro_id}，"
                    f"参数：{param_text}。用 macro 工具执行。"
                ),
                type="recurring",
                source="user",
                member_id=task.member_id or 0,
                trigger_spec=task.trigger_spec,
                dedup_key=f"legacy-macro:{task.id}",
                category="macro",
            )
            async with session_scope() as session:
                row = await session.get(AutonomousTask, task.id)
                row.is_active = False
            converted += 1
            logger.info(
                "[Scheduler] legacy macro row %s → ProjectTask (recurring)", task.id
            )
        if converted:
            logger.info("[Scheduler] converted %d legacy macro row(s)", converted)
        return converted

    @staticmethod
    async def dispatch_task(task_id: int):
        """
        Dispatch a single autonomous task（值守轮巡触发器专用）。

        AutonomousTask 已收缩为纯定时器：只有 provision 建的值守轮巡行。
        轮巡是机械采集（不烧 LLM、无验收语义），进程内直接执行，
        不进 ProjectTask 队列（串行 drain 会被慢轮巡互堵）。
        """
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                return

            from app.core.channel.duty.scheduler import task_is_duty

            if not task_is_duty(task.params_template):
                # 非值守行 = 迁移漏网的历史残留（正常应为墓碑），防御性日志
                logger.warning(
                    "[Scheduler] non-duty row %s reached dispatch (legacy residue?), skip",
                    task.id,
                )
                return

            # Update last run and next run
            task.last_run_at = datetime.now(timezone.utc)
            task.next_run_at = SchedulerService.calculate_next_run(task.trigger_spec, task.last_run_at)

            from app.core.channel.duty.scheduler import (
                run_duty_poll_with_release,
                try_claim_inflight,
            )

            kind = task.params_template.get("kind")
            # 防积压：该 (project_id, kind) 已在飞（排队中或执行中）→ 跳过本轮
            # 投递，只推进 next_run_at，不重复执行。执行结束由
            # run_duty_poll_with_release finally 释放登记。
            if not try_claim_inflight(task.project_id, kind):
                logger.info(f"[Scheduler] Duty task {task.id} in-flight (project={task.project_id}, kind={kind}), skip dispatch")
                return

            await run_duty_poll_with_release(project_id=task.project_id, kind=kind)
            logger.info(f"[Scheduler] Ran duty task {task.id} (next run: {task.next_run_at})")
        # 单 drainer 化同时关闭了 API/worker 双 tick 的跨进程双派发窗口。

    @staticmethod
    def calculate_next_run(trigger_spec: str, base_time: datetime) -> datetime:
        """
        Calculate the next run time based on trigger spec.
        """
        # 1. Cron
        if croniter.is_valid(trigger_spec):
            iter = croniter(trigger_spec, base_time)
            return iter.get_next(datetime)

        # 2. Interval (e.g. 'interval:3600')
        if trigger_spec.startswith("interval:"):
            try:
                seconds = int(trigger_spec.split(":")[1])
                return datetime.fromtimestamp(base_time.timestamp() + seconds, tz=timezone.utc)
            except (IndexError, ValueError):
                pass

        # Default fallback (1 hour if invalid)
        return datetime.fromtimestamp(base_time.timestamp() + 3600, tz=timezone.utc)

