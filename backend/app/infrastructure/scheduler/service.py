import logging
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from sqlalchemy import select

from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill
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
        Called every minute by Celery Beat.
        """
        now = datetime.now(timezone.utc)
        
        async with session_scope() as session:
            # 1. Catch active & due tasks (fetch only IDs)
            stmt = select(AutonomousTask.id).where(
                AutonomousTask.is_active == True,
                AutonomousTask.is_dead_letter == False,
                AutonomousTask.next_run_at <= now
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
                logger.error(f"[Scheduler] Failed to dispatch task {task_id}: {e}")

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
            
            # Prepare payload for background agent
            # Instead of just running the macro, we start an agent session
            # so it can use 'agentic' adaptive logic if the macro fails.
            from app.core.engine.tasks import run_autonomous_task_execution
            
            # Dispatch as Celery task
            run_autonomous_task_execution.delay(
                task_id=task.id,
                project_id=task.project_id
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
        skill_id: int,
        trigger_spec: str,
        params: dict[str, Any] | None = None,
        project_id: int | None = None
    ) -> int:
        """
        Programmatic entry for Agent to register a new recurring delegation.
        """
        async with session_scope() as session:
            # Validate skill
            skill = await session.get(LearnedSkill, skill_id)
            if not skill:
                raise ValueError(f"Skill ID {skill_id} not found.")

            task = AutonomousTask(
                member_id=0,
                intent_description=intent_description,
                skill_id=skill_id,
                trigger_spec=trigger_spec,
                params_template=params,
                project_id=project_id,
                next_run_at=SchedulerService.calculate_next_run(trigger_spec, datetime.now(timezone.utc))
            )
            session.add(task)
            await session.flush()
            return task.id
