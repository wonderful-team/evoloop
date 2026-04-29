"""
Term Bank Maintenance Service

Handles periodic decay and cleanup of stale domain terms.
Integrated into MemoryManager.run_maintenance() lifecycle.
"""

import logging

from app.core.memory.domain_terms import DomainTermBank

logger = logging.getLogger(__name__)


class TermBankMaintenanceService:
    """
    Maintenance service for domain term bank lifecycle.

    Runs decay on stale terms and returns an audit log.
    """

    def __init__(self, term_bank: DomainTermBank, half_life_days: int = 30):
        self._term_bank = term_bank
        self._half_life_days = half_life_days

    async def run(self, project_id: int | None = None) -> dict:
        """
        Execute term bank maintenance for a project.

        Returns:
            Dict with decay statistics.
        """
        try:
            removed = await self._term_bank.decay(
                project_id=project_id,
                half_life_days=self._half_life_days,
            )
            logger.info(
                f"[TermBankMaintenance] Decayed {len(removed)} stale terms "
                f"for project={project_id}"
            )
            return {
                "status": "completed",
                "removed_count": len(removed),
                "removed_terms": removed,
            }
        except Exception as e:
            logger.warning(f"[TermBankMaintenance] Failed for project={project_id}: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
