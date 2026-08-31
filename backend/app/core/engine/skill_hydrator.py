"""
Skill Hydration — Middleware for skill/SOP discovery and hydration.

Unifies 'Eager' (JIT injection) and 'Lazy' (Tool-based) patterns.
"""

import logging
from typing import Any

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class SkillHydrator:
    """
    Middleware to handle skill/SOP discovery and hydration for agent nodes.
    Unifies 'Eager' (JIT injection) and 'Lazy' (Tool-based) patterns.
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

    @staticmethod
    async def hydrate(
        state: AgentState,
        topic: str,
        namespace_context: str | None = None,
        mode: str = "eager",  # "eager" or "lazy"
    ) -> list[Any]:
        """
        Fetch relevant skills based on the topic and mode.
        If eager, returns full LearnedSkill objects.
        If lazy, returns a lightweight list of dicts (name, description) for an index.
        """
        from app.core.learning.skills.discovery import skill_discovery

        if mode == "lazy":
            logger.info(
                f"[Hydrator] Lazy mode for topic: {topic}. Fetching namespace index."
            )
            return await skill_discovery.get_namespace_index(namespace_context)

        # Eager mode: Fetch and return full SOP instructions
        logger.info(f"[Hydrator] Eagerly hydrating skills for query: {topic}")
        match, relevant, reasoning = await skill_discovery.exact_search(
            query=topic, namespace_context=namespace_context
        )

        # exact_search handles both numeric ID, exact name, and namespace/ prefix
        return relevant

    @staticmethod
    async def get_node_skills(state: AgentState, node_name: str) -> list[Any]:
        """
        Helper to get skills tailored for a specific agent role.
        """
        topic = state.session_goal or ""

        return await SkillHydrator.hydrate(
            state, topic, mode="eager"
        )
