"""
Skill Hydration — Middleware for skill/SOP discovery and hydration.

Unifies 'Eager' (JIT injection) and 'Lazy' (Tool-based) patterns.
"""

import logging
from typing import Any

from sqlalchemy import select

from app.core.engine.state import AgentState
from app.infrastructure.database.sql.database import session_scope

logger = logging.getLogger(__name__)


class SkillHydrator:
    """
    Middleware to handle skill/SOP discovery and hydration for agent nodes.
    Unifies 'Eager' (JIT injection) and 'Lazy' (Tool-based) patterns.
    """

    @staticmethod
    async def get_skill_by_id(skill_id: int) -> Any | None:
        """
        Fetch a single skill by its ID.
        Used for direct skill lookup without search overhead.
        """
        from app.models.learning import LearnedSkill

        if not skill_id:
            return None

        try:
            async with session_scope() as session:
                stmt = select(LearnedSkill).where(
                    LearnedSkill.id == skill_id,
                    LearnedSkill.is_active == True
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[Hydrator] Failed to fetch skill {skill_id}: {e}")
            return None

    @staticmethod
    async def hydrate(
        state: AgentState,
        topic: str,
        namespace_context: str | None = None,
        mode: str = "eager"  # "eager" or "lazy"
    ) -> list[Any]:
        """
        Fetch relevant skills based on the topic and mode.
        If eager, returns full LearnedSkill objects.
        If lazy, returns a lightweight list of dicts (name, description) for an index.
        """
        from app.core.learning.discovery import skill_discovery

        if mode == "lazy":
            logger.info(f"[Hydrator] Lazy mode for topic: {topic}. Fetching namespace index.")
            return await skill_discovery.get_namespace_index(namespace_context)

        # Eager mode: Fetch and return full SOP instructions
        execution_ticket = state.ticket
        # skill_ids takes priority from the ticket if present, otherwise fallback to topic
        query = (execution_ticket.skill_ids[0] if execution_ticket.skill_ids else None) if execution_ticket else None
        if not query:
            query = topic

        logger.info(f"[Hydrator] Eagerly hydrating skills for query: {query}")
        match, relevant, reasoning = await skill_discovery.exact_search(
            query=query,
            namespace_context=namespace_context
        )

        # exact_search handles both numeric ID, exact name, and namespace/ prefix
        return relevant

    @staticmethod
    async def get_node_skills(state: AgentState, node_name: str) -> list[Any]:
        """
        Helper to get skills tailored for a specific node type.
        """
        execution_ticket = state.ticket
        topic = execution_ticket.topic or "" if execution_ticket else ""
        namespace_context = execution_ticket.namespace_context if execution_ticket else None

        # In Unified Graph (v5), we default to 'eager' hydration for standard Workers.
        # But for sub-tasks, we skip eager hydration to prevent cognitive overload
        # unless a specific skill_hint is provided.
        agent_config = execution_ticket.agent_config if execution_ticket else None
        if state.is_subtask and not (agent_config and agent_config.skill_hint):
            logger.info(f"[Hydrator] Skipping eager hydration for subtask: {topic}")
            return []

        return await SkillHydrator.hydrate(state, topic, namespace_context=namespace_context, mode="eager")
