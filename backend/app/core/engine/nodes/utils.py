import logging
from typing import Any

from app.core.engine.state import AgentState
from app.core.learning.discovery import skill_discovery

logger = logging.getLogger(__name__)


class SkillHydrator:
    """
    Middleware to handle skill/SOP discovery and hydration for agent nodes.
    Unifies 'Eager' (JIT injection) and 'Lazy' (Tool-based) patterns.
    """

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
        if mode == "lazy":
            logger.info(f"[Hydrator] Lazy mode for topic: {topic}. Fetching namespace index.")
            return await skill_discovery.get_namespace_index(namespace_context)

        # Eager mode: Fetch and return full SOP instructions
        logger.info(f"[Hydrator] Eagerly hydrating skills for topic: {topic}")
        match, relevant, reasoning = await skill_discovery.exact_search(
            query=topic,
            namespace_context=namespace_context
        )

        # exact_search returns (SkillMatch | None, List[LearnedSkill])
        # If there's a match, relevant already contains the skill object.
        return relevant

    @staticmethod
    async def get_node_skills(state: AgentState, node_name: str) -> list[Any]:
        """
        Helper to get skills tailored for a specific node type.
        """
        execution_ticket = state.get("execution_ticket") or {}
        topic = execution_ticket.get("topic", "")
        # Track 8: Dynamic Namespace Mounting
        namespace_context = execution_ticket.get("namespace_context")

        # In Unified Graph (v5), we default to 'eager' hydration for standard Workers.
        # But for sub-tasks, we skip eager hydration to prevent cognitive overload
        # unless a specific skill_hint is provided. 
        if state.get("is_subtask") and not execution_ticket.get("agent_config", {}).get("skill_hint"):
            logger.info(f"[Hydrator] Skipping eager hydration for subtask: {topic}")
            return []

        # Future optimization: allow Supervisor to specify 'lazy' via Ticket parameters.
        is_lazy = execution_ticket.get("parameters", {}).get("lazy_hydration", False)
        mode = "lazy" if is_lazy else "eager"

        return await SkillHydrator.hydrate(state, topic, namespace_context=namespace_context, mode=mode)
