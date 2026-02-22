import logging
from typing import Any, List, Optional, Tuple
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.learning.discovery import skill_discovery, SkillMatch
from app.models.learning import LearnedSkill

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
        namespace_context: Optional[str] = None,
        mode: str = "eager"  # "eager" or "lazy"
    ) -> List[Any]:
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
        match, relevant = await skill_discovery.exact_search(
            query=topic, 
            namespace_context=namespace_context
        )
        
        # exact_search returns (SkillMatch | None, List[LearnedSkill])
        # If there's a match, relevant already contains the skill object.
        return relevant

    @staticmethod
    async def get_node_skills(state: AgentState, node_name: str) -> List[Any]:
        """
        Helper to get skills tailored for a specific node type.
        """
        execution_ticket = state.get("execution_ticket") or {}
        topic = execution_ticket.get("topic", "")
        # Track 8: Dynamic Namespace Mounting
        namespace_context = execution_ticket.get("namespace_context")
        
        # Default behavior: Operator is Lazy, Specialist is Eager
        if node_name.lower() == "operator":
            return await SkillHydrator.hydrate(state, topic, namespace_context=namespace_context, mode="lazy")
        else:
            return await SkillHydrator.hydrate(state, topic, namespace_context=namespace_context, mode="eager")
