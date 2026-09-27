"""
Skill Hydration — Middleware for skill/SOP discovery and hydration.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillHydrator:
    """
    Middleware to handle skill/SOP discovery and hydration for agent nodes.
    """

    @staticmethod
    async def get_skill_by_id(skill_id: int) -> Any | None:
        """
        Fetch a single visible skill by its ID.
        Used for direct skill lookup without search overhead.
        """
        from app.core.learning.skills.repository import skill_repository

        if not skill_id:
            return None

        try:
            return await skill_repository.get_by_id(skill_id, visible_only=True)
        except Exception as e:
            logger.exception(f"[Hydrator] Failed to fetch skill {skill_id}: {e}")
            return None
