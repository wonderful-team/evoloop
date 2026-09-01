import logging
from datetime import datetime, timezone
from typing import Any

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
        Called every 60s by engine_scheduler_tick_periodic (Huey periodic "* * * * *").
        """
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

    @staticmethod
    async def dispatch_task(task_id: int):
        """
        Dispatch a single autonomous task to the background executor.
        """
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                return

            # Update last run and next run
            task.last_run_at = datetime.now(timezone.utc)
            task.next_run_at = SchedulerService.calculate_next_run(task.trigger_spec, task.last_run_at)

            # 值守任务（params_template 带 duty_channel 标记）走轻量轮巡路径，
            # 不依赖 Android 设备池，直接 poll_once → dispatch。
            # 值守轮巡**不进持久队列**：在 tick 进程内直接 await 执行，
            # 避免 Huey 队列里残留旧 run_duty_poll 任务、重启后重复执行。
            from app.core.channel.duty.scheduler import task_is_duty, try_claim_inflight

            if task_is_duty(task.params_template):
                from app.core.channel.duty.scheduler import run_duty_poll_with_release

                kind = task.params_template.get("kind")
                # 防积压：该 (project_id, kind) 已在飞（排队中或执行中）→ 跳过本轮
                # 投递，只推进 next_run_at，不重复执行。执行结束由
                # run_duty_poll_with_release finally 释放登记。
                if not try_claim_inflight(task.project_id, kind):
                    logger.info(f"[Scheduler] Duty task {task.id} in-flight (project={task.project_id}, kind={kind}), skip dispatch")
                    return

                await run_duty_poll_with_release(project_id=task.project_id, kind=kind)
                logger.info(f"[Scheduler] Ran duty task {task.id} (next run: {task.next_run_at})")
                return

            # 宏任务：关联了 macro_id → 直接执行宏（不经 agent、不强制设备池）。
            # 宏内部按 source 处理 web/desktop/mobile 执行器；device 由执行器解析。
            if task.macro_id is not None:
                await SchedulerService.dispatch_macro_task(task)
                return

            # Prepare payload for background agent
            # Instead of just running the macro, we start an agent session
            # so it can use 'agentic' adaptive logic if the macro fails.
            from app.core.engine.tasks import run_autonomous_task_execution

            # Dispatch as Celery task
            run_autonomous_task_execution.delay(task_id=task.id, project_id=task.project_id)

            logger.info(f"[Scheduler] Dispatched task {task.id} (next run: {task.next_run_at})")

    @staticmethod
    async def dispatch_macro_task(task: AutonomousTask):
        """Execute a macro-linked autonomous task directly (no agent session).

        Loads the macro by id (scoped to the task's project) and runs it via
        MacroEngine with the task's params template. Logs the outcome and tracks
        consecutive failures / dead-letter state.
        """
        try:
            from app.core.learning.macro import load_macro
            from app.core.learning.macro.engine import MacroEngine
            from app.utils.id import unique_id

            macro = await load_macro(
                int(task.macro_id), project_id=task.project_id
            )
            if macro is None:
                raise ValueError(f"Macro {task.macro_id} not found for task {task.id}")

            thread_id = unique_id("sched", task.id)
            result = await MacroEngine.run(
                thread_id=thread_id,
                macro=macro,
                params=dict(task.params_template or {}),
                project_id=task.project_id or 0,
            )

            logger.info(
                "[Scheduler] Macro task %s executed macro %s: success=%s status=%s",
                task.id,
                task.macro_id,
                result.success,
                result.status,
            )
            if not result.success:
                raise RuntimeError(
                    result.message or f"Macro {task.macro_id} failed (status={result.status})"
                )
        except Exception as e:
            logger.exception("[Scheduler] Macro task %s failed: %s", task.id, e)
            # 失败计数 + dead-letter 兜底，与 agent 路径对齐
            await SchedulerService._record_task_failure(task.id, str(e))
            return

        await SchedulerService._clear_task_failures(task.id)

    @staticmethod
    async def _record_task_failure(task_id: int, reason: str):
        """Increment consecutive failures; dead-letter the task when exhausted."""
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                return
            task.consecutive_failures += 1
            task.last_failure_reason = reason
            if task.consecutive_failures >= (task.max_retries or 3):
                task.is_active = False
                task.is_dead_letter = True

    @staticmethod
    async def _clear_task_failures(task_id: int):
        """Reset consecutive failure counter after a successful run."""
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                return
            task.consecutive_failures = 0
            task.last_failure_reason = None

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

    @staticmethod
    async def register_task(
        intent_description: str,
        skill_ids: list[int] | None = None,
        macro_id: int | None = None,
        trigger_spec: str = "interval:3600",
        params: dict[str, Any] | None = None,
        project_id: int | None = None,
    ) -> int:
        """
        Programmatic entry for Agent to register a new recurring delegation.
        """
        skill_ids = skill_ids or []
        async with session_scope() as session:
            # Validate skills (if any)
            if skill_ids:
                from app.core.learning.skills.repository import skill_repository

                missing = await skill_repository.validate_ids(skill_ids, db=session)
                if missing:
                    raise ValueError(f"Skill IDs {sorted(missing)} not found.")

            # Validate macro (if any)
            if macro_id is not None:
                from app.core.learning.macro import load_macro

                macro = await load_macro(int(macro_id), project_id=project_id)
                if macro is None:
                    raise ValueError(f"Macro {macro_id} not found (project={project_id}).")

            task = AutonomousTask(
                member_id=0,
                intent_description=intent_description,
                skill_ids=skill_ids,
                macro_id=macro_id,
                trigger_spec=trigger_spec,
                params_template=params,
                project_id=project_id,
                next_run_at=SchedulerService.calculate_next_run(trigger_spec, datetime.now(timezone.utc))
            )
            session.add(task)
            await session.flush()
            return task.id
