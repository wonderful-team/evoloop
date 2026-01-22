import logging
import os

from langchain_core.tools import tool

from app.constants import YAML_EXTENSIONS
from app.core.engine.graph_builder import GraphBuilder
from app.i18n.service import i18n

logger = logging.getLogger("evoloop.orchestration")

# Standard location for Agent Configs
AGENTS_DIR = os.path.join(os.path.dirname(__file__), "../workflows/config")


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, str] = {}  # name -> path
        self.scan_skills()

    def scan_skills(self):
        """
        Scan the agents configuration directory for valid YAML files.
        """
        if not os.path.exists(AGENTS_DIR):
            logger.warning(f"Agents directory not found: {AGENTS_DIR}")
            return

        for filename in os.listdir(AGENTS_DIR):
            if any(filename.endswith(ext) for ext in YAML_EXTENSIONS):
                name = os.path.splitext(filename)[0]
                self._skills[name] = os.path.join(AGENTS_DIR, filename)

        logger.info(f"Loaded {len(self._skills)} skills: {list(self._skills.keys())}")

    def get_skill_path(self, skill_name: str) -> str | None:
        return self._skills.get(skill_name)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


# Global Instance
_registry = SkillRegistry()


@tool
async def delegate_task(skill_name: str, task_input: dict) -> dict:
    """
    Delegates a sub-task to a specialized independent Agent (Skill).
    This creates a dynamic sub-graph execution.

    Args:
        skill_name: The name of the agent to spawn (e.g., 'researcher', 'coder').
        task_input: A dictionary of initial state inputs (e.g., {'messages': ['Analyze this']}).
    """
    config_path = _registry.get_skill_path(skill_name)
    if not config_path:
        # Fallback: Rescan just in case
        _registry.scan_skills()
        config_path = _registry.get_skill_path(skill_name)

    if not config_path:
        available = ", ".join(_registry.list_skills())
        return {
            "error": i18n.get(
                "prompts.orchestration.skill_not_found",
                name=skill_name,
                available=available,
            )
        }

    try:
        logger.info(f"Orchestrator delegating task to: {skill_name}")

        # Build the agent graph on the fly
        builder = GraphBuilder()
        # We assume independent execution (no checkpointer shared for now, or maybe passing None)
        agent_app = builder.build(config_path)

        # Execute
        # Note: 'task_input' must match the State Schema of the target agent.
        # Most universal agents use 'messages' and 'scratchpad'.
        result = await agent_app.ainvoke(task_input)

        # We return the FINAL state.
        # The caller (Manager) must decide what to extract.
        return result

    except Exception as e:
        logger.error(f"Delegation failed: {e}")
        return {
            "error": i18n.get(
                "prompts.orchestration.delegation_failed", name=skill_name, error=str(e)
            )
        }


def find_skills(_query: str) -> str:
    """
    Helper for the LLM to know what skills exist.
    """
    # Simple list for now. Could be semantic search later.
    return i18n.get(
        "prompts.orchestration.available_skills",
        skills=", ".join(_registry.list_skills()),
    )
