"""
Memory Maintenance - Automated memory cleanup using Agent Engine.

Daily at 2:00 AM, checks if maintenance is needed (3+ days or 100+ memories).
If needed, runs a maintenance agent to evaluate and cleanup memories.

Logs only the timestamp of maintenance runs to ~/.evoloop/memory/.maintenance
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.memory.lifespan import MemoryLifespanManager
from app.infrastructure.queue.factory import periodic_task

logger = logging.getLogger(__name__)


class MemoryMaintenanceAgent:
    """
    Agent-based memory maintenance.
    
    Runs in isolated thread, cleans up after itself.
    Only logs timestamp of execution.
    """

    def __init__(self):
        self.thread_id = f"maint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.log_file = Path(settings.BRAIN_MEMORY_ROOT) / ".maintenance"

    async def run(self):
        """Execute maintenance."""
        start_time = datetime.utcnow()
        logger.info(f"[Maintenance] Starting: {self.thread_id}")

        try:
            # Initialize memory container if needed (global singleton manager)
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()

            container = MemoryLifespanManager.get_container()
            manager = container.memory_manager

            # Run unified maintenance (Pruning, Consolidation, MEMORY.md)
            results = await manager.run_maintenance()

            # Log completion time
            self._log_time(start_time)

            logger.info(f"[Maintenance] Completed: {self.thread_id} - Pruned {results.get('pruning_count')} items")

            return results

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[Maintenance] Failed: {e}")
            # Still try to cleanup
            try:
                await self._cleanup_thread()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
            raise

    def _log_time(self, time: datetime):
        """Log maintenance timestamp (one line per run)."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\n")

    async def _cleanup_thread(self):
        """Delete all messages from maintenance thread (isolation)."""
        try:
            from sqlalchemy import delete

            from app.infrastructure.database import session_scope
            from app.models.conversation import Message

            async with session_scope() as session:
                result = await session.execute(
                    delete(Message).where(Message.thread_id == self.thread_id)
                )

                deleted = result.rowcount
                logger.debug(f"[Maintenance] Cleaned {deleted} messages from {self.thread_id}")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[Maintenance] Cleanup warning: {e}")

    def get_last_time(self) -> datetime | None:
        """Get last maintenance time from log file."""
        if not self.log_file.exists():
            return None

        try:
            with open(self.log_file, encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_line = lines[-1]
                    return datetime.strptime(last_line, "%Y-%m-%d %H:%M")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[Maintenance] Failed to read log: {e}")

        return None

    def count_hot_memories(self) -> int:
        """Count hot memory entries (markdown files in memory dir)."""
        memory_dir = Path(settings.BRAIN_MEMORY_ROOT)
        if not memory_dir.exists():
            return 0

        # Count all .md files except MEMORY.md and logs
        count = 0
        for path in memory_dir.rglob("*.md"):
            if path.name == "MEMORY.md":
                continue
            if "logs" in str(path):
                continue
            count += 1

        return count


class MaintenanceScheduler:
    """
    Schedules memory maintenance based on time and capacity.
    
    Triggers when:
    - 3+ days since last maintenance, OR
    - 100+ hot memory entries
    """

    def __init__(self):
        self.agent = MemoryMaintenanceAgent()

    async def should_run(self) -> bool:
        """Check if maintenance should run."""
        # Check time condition
        last_time = self.agent.get_last_time()
        if last_time:
            days_since = (datetime.utcnow() - last_time).days
            if days_since >= 7:
                logger.info(f"[Maintenance] Trigger: {days_since} days since last")
                return True
            if days_since < 3:
                return False  # Minimum 3 days

        # Check capacity condition
        hot_count = self.agent.count_hot_memories()
        if hot_count > 100:
            logger.info(f"[Maintenance] Trigger: {hot_count} hot memories")
            return True

        # First run
        if not last_time:
            logger.info("[Maintenance] Trigger: first run")
            return True

        return False

    async def run(self):
        """Run maintenance if needed."""
        if not await self.should_run():
            logger.info("[Maintenance] Skip: conditions not met")
            return None

        return await self.agent.run()


# Daily scheduled task: 2:00 AM
# DISABLED by default — set MEMORY_MAINTENANCE_ENABLED=True in settings to enable.
# Reason: run_maintenance() triggers irreversible semantic pruning of the memory store.
_MAINTENANCE_ENABLED = settings.MEMORY_MAINTENANCE_ENABLED

if _MAINTENANCE_ENABLED:
    @periodic_task(cron="0 2 * * *", name="memory_maintenance")
    def scheduled_memory_maintenance():
        """
        Daily maintenance check at 2:00 AM.

        Checks if maintenance is needed (3+ days or 100+ memories).
        If needed, runs the maintenance agent.

        Enable via: MEMORY_MAINTENANCE_ENABLED=True in settings.
        """
        async def _run():
            try:
                scheduler = MaintenanceScheduler()
                result = await scheduler.run()
                return {"triggered": result is not None}
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[Maintenance] Scheduled task failed: {e}")
                return {"triggered": False, "error": str(e)}

        return asyncio.run(_run())
else:
    logger.debug("[Maintenance] Scheduled memory maintenance is DISABLED. Set MEMORY_MAINTENANCE_ENABLED=True to enable.")


# Convenience functions for manual trigger / CLI
def trigger_maintenance():
    """Manually trigger maintenance (for CLI/admin use)."""
    async def _run():
        agent = MemoryMaintenanceAgent()
        return await agent.run()

    return asyncio.run(_run())


def get_maintenance_status():
    """Get maintenance status for CLI."""
    agent = MemoryMaintenanceAgent()
    last_time = agent.get_last_time()
    hot_count = agent.count_hot_memories()

    status = {
        "last_maintenance": last_time.isoformat() if last_time else None,
        "hot_memory_count": hot_count,
        "days_since": None,
    }

    if last_time:
        status["days_since"] = (datetime.utcnow() - last_time).days

    return status
