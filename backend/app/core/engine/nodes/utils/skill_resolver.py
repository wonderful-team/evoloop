"""
Skill resolution utilities for Worker node.

Handles fallback SOP injection and skill loading by ID.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.engine.skill_hydrator import SkillHydrator
from app.infrastructure.database import session_scope

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
                from app.models.learning import LearnedSkill

                async with session_scope() as session:
                    stmt = select(LearnedSkill).where(LearnedSkill.id == original_skill_id)
                    result = await session.execute(stmt)
                    skill = result.scalar_one_or_none()
                    if skill and skill.instructions:
                        if not any(s.id == original_skill_id for s in relevant_sops):
                            relevant_sops.insert(0, skill)

                    healer_stmt = select(LearnedSkill).where(LearnedSkill.name == "Macro Recovery Specialist")
                    healer_result = await session.execute(healer_stmt)
                    generic_healer = healer_result.scalar_one_or_none()
                    if generic_healer:
                        if not any(s.id == generic_healer.id for s in relevant_sops):
                            relevant_sops.append(generic_healer)
            except (ImportError, SQLAlchemyError) as e:
                logger.error(f"[Worker] Failed to fetch fallback skill instructions: {e}")
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
