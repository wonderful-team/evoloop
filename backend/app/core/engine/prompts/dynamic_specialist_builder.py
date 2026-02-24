import os
import logging
from typing import Any
from jinja2 import Environment, FileSystemLoader

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
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

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
        """Constructs the user message that initiates the task."""
        topic = self.ticket.get("topic") or "General Task"
        criteria = "\n".join([f"- {c}" for c in self.ticket.get("acceptance_criteria", [])])
        params = self.ticket.get("parameters", {})
        param_context = ""
        if params:
            param_context = "\n**Execution Parameters**:\n" + "\n".join([f"- {k}: {v}" for k, v in params.items()])

        return f"""### MISSION TICKET
**Goal**: {topic}

**Acceptance Criteria**:
{criteria}
{param_context}

Please execute this mission now. Use your tools."""

    def _prepare_knowledge_blocks(self) -> list[str]:
        if not self.skills:
            return []

        blocks = []
        for i, skill in enumerate(self.skills):
            is_primary = (i == 0)
            header = "### 🚨 [ACTIVE MISSION SOP]" if is_primary else "### 📘 Related Reference SOP"

            block = f"{header}: {skill.name}\n"
            if is_primary:
                block += "You MUST treat the following instructions as a strict state-machine. Read Phase 1. Execute. Verify. Only proceed to Phase 2 upon success.\n\n"

            if skill.description:
                block += f"**Description**: {skill.description}\n"
            if skill.instructions:
                block += f"**Expert Guide (操作指南)**:\n{skill.instructions}\n"
            blocks.append(block)
        return blocks
