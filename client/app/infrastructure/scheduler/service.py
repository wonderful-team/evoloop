import logging
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from sqlalchemy import select, update

from app.core.config import settings
from app.infrastructure.database.sql.database import session_scope
from app.models.scheduler import AutonomousTask


logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Main service for orchestrating autonomous tasks and periodic agent delegations.

    NOTE: In client mode, this service is disabled. Autonomous tasks are managed by the cloud scheduler.
    """

    @staticmethod
    async def tick():
        """
        Poll for due tasks and dispatch them to the background worker.
        Called every minute by Celery Beat.

        NOTE: Disabled in client mode (learning module moved to cloud).
        """
        # REMOVED: Client mode does not support local autonomous task execution
        # Cloud scheduler handles this on the server side
        logger.debug("[Scheduler] Local scheduler tick skipped (client mode)")
        return

    @staticmethod
    async def dispatch_task(task_id: int):
        """
        Dispatch a single autonomous task to the background executor.

        NOTE: Disabled in client mode.
        """
        # REMOVED: Client mode does not support local task dispatch
        logger.debug(f"[Scheduler] Task dispatch skipped for {task_id} (client mode)")
        return

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

        NOTE: In client mode, this forwards to cloud API. Local registration is disabled.
        """
        # REMOVED: Local LearnedSkill validation (moved to cloud)
        # Client should use cloud API for task registration
        raise NotImplementedError(
            "Local task registration is disabled in client mode. "
            "Please use the cloud scheduler API."
        )
