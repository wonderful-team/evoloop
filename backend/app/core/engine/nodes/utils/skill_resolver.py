"""
Skill resolution utilities for Worker node.

Handles fallback SOP injection and skill loading by ID.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from app.core.engine.skill_hydrator import SkillHydrator

if TYPE_CHECKING:
    from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


class SkillResolver:
    """Resolves and enriches skill/SOP configurations for Worker execution."""

    @staticmethod
    async def inject_fallback_sops(relevant_sops: list["LearnedSkill"], config: dict) -> list["LearnedSkill"]:
        """Inject fallback SOPs based on metadata (e.g., original_skill_id for retry)."""
        metadata = config.get("metadata", {})
        original_skill_id = metadata.get("original_skill_id")
        if original_skill_id:
            try:
                from app.core.learning.skills.repository import skill_repository

                skill = await skill_repository.get_by_id(original_skill_id)
                if skill and skill.instructions:
                    if not any(s.id == original_skill_id for s in relevant_sops):
                        relevant_sops.insert(0, skill)

                generic_healer = await skill_repository.get_by_name(
                    "Macro Recovery Specialist"
                )
                if generic_healer:
                    if not any(s.id == generic_healer.id for s in relevant_sops):
                        relevant_sops.append(generic_healer)
            except (ImportError, SQLAlchemyError) as e:
                logger.exception(f"[Worker] Failed to fetch fallback skill instructions: {e}")
        return relevant_sops

    @staticmethod
    async def load_skills_by_ids(skill_ids: list[int]) -> list["LearnedSkill"]:
        """Load skills by ID list (for multi-skill workflow)."""
        skills = []
        for sid in skill_ids:
            skill = await SkillHydrator.get_skill_by_id(sid)
            if skill:
                skills.append(skill)
            else:
                raise ValueError(f"Required Skill ID {sid} is not found or inactive. Execution aborted.")
        return skills
