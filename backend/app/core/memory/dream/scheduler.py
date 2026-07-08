"""
DreamScheduler — triggers Deep Dream cycles on schedule or idle.

Mirrors the MaintenanceScheduler pattern but for dream distillation:
- Runs during idle periods (configurable cron, default 3 AM)
- Can be triggered manually via CLI
- Writes dream records to ~/.evoloop/memory/.dream/ for audit
- Disabled by default (DEEP_DREAM_ENABLED setting)
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings

from .distiller import DeepDreamDistiller
from .schemas import DreamRecord

logger = logging.getLogger(__name__)

_DREAM_DIR = Path(settings.BRAIN_MEMORY_ROOT) / ".dream"


class DreamScheduler:
    """Schedules and triggers Deep Dream cycles."""

    def __init__(self, memory_manager: Any | None = None):
        self._memory_manager = memory_manager

    def _get_manager(self) -> Any:
        if self._memory_manager is None:
            from app.core.memory.lifespan import MemoryLifespanManager
            self._memory_manager = MemoryLifespanManager.get_manager()
        return self._memory_manager

    async def should_run(self) -> bool:
        """Check if a dream cycle should run based on last run time."""
        last = self._get_last_run_time()
        if last is None:
            return True
        hours_since = (datetime.now() - last).total_seconds() / 3600
        return hours_since >= 24

    async def should_run_cross_project(self) -> bool:
        """Check if a cross-project dream cycle should run (weekly)."""
        last = self._get_last_run_time(key="cross_project")
        if last is None:
            return True
        hours_since = (datetime.now() - last).total_seconds() / 3600
        return hours_since >= 168  # 7 days

    async def run_cross_project(
        self,
        days_back: int = 14,
        max_episodes: int = 40,
    ) -> DreamRecord | None:
        """
        Execute a cross-project dream cycle.

        Loads episodes from ALL projects (project_id=None), distills insights,
        and promotes cross-project patterns to global (project_id=0) memory.
        """
        if not await self.should_run_cross_project():
            logger.info("[Dream] Skip cross-project: last run too recent")
            return None

        manager = self._get_manager()
        distiller = DeepDreamDistiller(manager)

        started = datetime.now()
        record = DreamRecord(
            id=f"dream_cross_{started.strftime('%Y%m%d_%H%M%S')}",
            started_at=started.isoformat(),
        )

        try:
            result = await distiller.dream(
                project_id=None,  # Cross-project: loads from all projects
                days_back=days_back,
                max_episodes=max_episodes,
            )

            # Promote cross-project recurring concepts to global
            promoted = await distiller.promote_cross_project_concepts()

            record.finished_at = datetime.now().isoformat()
            record.episodes_count = result.episodes_replayed
            record.insights_count = len(result.insight_ids) + promoted
            record.insight_ids = result.insight_ids
            if result.error:
                record.error = result.error
            logger.info(
                "[Dream] Cross-project cycle: %d episodes, %d insights, %d promoted",
                result.episodes_replayed,
                len(result.insight_ids),
                promoted,
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            record.finished_at = datetime.now().isoformat()
            record.error = str(e)
            logger.error("[Dream] Cross-project cycle failed: %s", e)

        self._save_record(record, key="cross_project")
        return record

    async def run(
        self,
        project_id: int | None = None,
        days_back: int = 7,
        max_episodes: int = 20,
    ) -> DreamRecord | None:
        """
        Execute a dream cycle.

        Returns:
            DreamRecord if run, None if skipped
        """
        if not await self.should_run():
            logger.info("[Dream] Skip: last run too recent")
            return None

        manager = self._get_manager()
        distiller = DeepDreamDistiller(manager)

        started = datetime.now()
        record = DreamRecord(
            id=f"dream_{started.strftime('%Y%m%d_%H%M%S')}",
            started_at=started.isoformat(),
        )

        try:
            result = await distiller.dream(
                project_id=project_id,
                days_back=days_back,
                max_episodes=max_episodes,
            )
            record.finished_at = datetime.now().isoformat()
            record.episodes_count = result.episodes_replayed
            record.insights_count = len(result.insight_ids)
            record.insight_ids = result.insight_ids
            if result.error:
                record.error = result.error
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            record.finished_at = datetime.now().isoformat()
            record.error = str(e)
            logger.error("[Dream] Cycle failed: %s", e)

        self._save_record(record)
        return record

    def _get_last_run_time(self, key: str = "default") -> datetime | None:
        """Read the last dream run timestamp from the dream log."""
        try:
            filename = "last_run.json" if key == "default" else f"last_run_{key}.json"
            log_file = _DREAM_DIR / filename
            if log_file.exists():
                data = json.loads(log_file.read_text())
                return datetime.fromisoformat(data["finished_at"])
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
        return None

    def _save_record(self, record: DreamRecord, key: str = "default") -> None:
        """Persist the dream record for audit."""
        try:
            _DREAM_DIR.mkdir(parents=True, exist_ok=True)
            filename = "last_run.json" if key == "default" else f"last_run_{key}.json"
            log_file = _DREAM_DIR / filename
            log_file.write_text(json.dumps({
                "id": record.id,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
                "episodes_count": record.episodes_count,
                "insights_count": record.insights_count,
                "insight_ids": record.insight_ids,
                "error": record.error,
            }, indent=2))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[Dream] Failed to save record: %s", e)


def trigger_dream(project_id: int | None = None) -> DreamRecord | None:
    """Manually trigger a dream cycle (for CLI/admin use)."""
    async def _run():
        scheduler = DreamScheduler()
        return await scheduler.run(project_id=project_id)

    return asyncio.run(_run())


def get_dream_status() -> dict:
    """Get dream status for CLI."""
    scheduler = DreamScheduler()
    last = scheduler._get_last_run_time()
    return {
        "last_dream": last.isoformat() if last else None,
        "hours_since": (datetime.now() - last).total_seconds() / 3600 if last else None,
        "should_run": asyncio.run(scheduler.should_run()) if last is None else (datetime.now() - last).total_seconds() / 3600 >= 24,
        "dream_dir": str(_DREAM_DIR),
    }
