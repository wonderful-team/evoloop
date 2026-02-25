import os
import logging
from typing import Any
from jinja2 import Environment, FileSystemLoader

from app.core.context import ContextManager, plugin_registry

logger = logging.getLogger(__name__)


class DynamicSpecialistPromptBuilder:
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents via Jinja2.
    """
    def __init__(
        self,
        agent_config: dict,
        ticket: dict,
        skills: list = None,
        known_packages: dict[str, str] = None,
        known_macos_apps: dict[str, str] = None,
        clipboard: list[dict[str, Any]] = None
    ):
        self.agent_config = agent_config
        self.ticket = ticket
        self.skills = skills or []
        self.known_packages = known_packages or {}
        self.known_macos_apps = known_macos_apps or {}
        self.clipboard = clipboard or []

        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build(self, config: Any = None) -> str:
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        knowledge_blocks = self._prepare_knowledge_blocks()

        template_vars = {
            "role_name": self.agent_config.get("role_name", "Specialist"),
            "instructions": self.agent_config.get("system_instructions", "You are a helpful assistant."),
            "environment": {
                "summaries": ctx.environment_summaries,
                "boundaries": ctx.active_boundaries,
                "spatial_awareness": ctx.spatial_awareness,
                "user_preferences": ctx.metadata.get("user_preferences", {}),
            },
            "known_packages": self.known_packages,
            "known_macos_apps": self.known_macos_apps,
            "knowledge_blocks": knowledge_blocks,
            "clipboard": self.clipboard,
        }

        try:
            template = self.env.get_template("dynamic_specialist.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering DynamicSpecialist template: {e}")
            return f"You are a Specialist. Error loading template: {e}"

    def build_mission_message(self) -> str:
        """Constructs the user message that initiates the task via Jinja2."""
        template_vars = {
            "topic": self.ticket.get("topic") or "General Task",
            "acceptance_criteria": self.ticket.get("acceptance_criteria", []),
            "parameters": self.ticket.get("parameters", {}),
        }
        try:
            template = self.env.get_template("fragments/mission_ticket.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering Mission Ticket: {e}")
            return f"### MISSION TICKET\nGoal: {template_vars['topic']}\nPlease execute this mission now."

    def _prepare_knowledge_blocks(self) -> list[str]:
        if not self.skills:
            return []

        blocks = []
        try:
            template = self.env.get_template("fragments/knowledge_block.j2")
            for i, skill in enumerate(self.skills):
                is_primary = (i == 0)
                block = template.render(skill=skill, is_primary=is_primary)
                blocks.append(block)
        except Exception as e:
            logger.error(f"Error rendering Knowledge Blocks: {e}")
            # Fallback to simple format if template fails
            for skill in self.skills:
                blocks.append(f"### Skill: {getattr(skill, 'name', 'Unknown')}\n{getattr(skill, 'instructions', '')}")
        
        return blocks
