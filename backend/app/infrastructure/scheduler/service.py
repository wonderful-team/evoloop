import logging
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from sqlalchemy import select

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
            stmt = select(AutonomousTask.id).where(
                AutonomousTask.is_active,
                not AutonomousTask.is_dead_letter,
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
            # run_duty_poll 只收 project_id，history 由系统按 local_path 推断（§6.8.3）。
            from app.core.channel.duty.scheduler import task_is_duty, try_claim_inflight

            if task_is_duty(task.params_template):
                from app.core.channel.duty.scheduler import run_duty_poll

                kind = task.params_template.get("kind")
                # 防积压：该 (project_id, kind) 已在飞（排队中或执行中）→ 跳过本轮
                # 投递，只推进 next_run_at，不重复入队。执行结束由 run_duty_poll
                # finally 释放登记。
                if not try_claim_inflight(task.project_id, kind):
                    logger.info(f"[Scheduler] Duty task {task.id} in-flight (project={task.project_id}, kind={kind}), skip dispatch")
                    return

                run_duty_poll.delay(
                    project_id=task.project_id,
                    kind=kind,
                )
                logger.info(
                    f"[Scheduler] Dispatched duty task {task.id} (next run: {task.next_run_at})"
                )
                return

            # Prepare payload for background agent
            # Instead of just running the macro, we start an agent session
            # so it can use 'agentic' adaptive logic if the macro fails.
            from app.core.engine.tasks import run_autonomous_task_execution

            # Dispatch as Celery task
            run_autonomous_task_execution.delay(
                task_id=task.id, project_id=task.project_id
            )

            logger.info(f"[Scheduler] Dispatched task {task.id} (next run: {task.next_run_at})")

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

            task = AutonomousTask(
                member_id=0,
                intent_description=intent_description,
                skill_ids=skill_ids,
                trigger_spec=trigger_spec,
                params_template=params,
                project_id=project_id,
                next_run_at=SchedulerService.calculate_next_run(trigger_spec, datetime.now(timezone.utc))
            )
            session.add(task)
            await session.flush()
            return task.id
