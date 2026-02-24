import logging
import os
from typing import Any

from jinja2 import Environment, FileSystemLoader
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.tools.manager import tool_manager
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class OperatorPromptBuilder:
    def __init__(self, state: AgentState, context: dict, project_id: int, skills: list[Any] | None = None):
        self.state = state
        self.context = context
        self.project_id = project_id
        self.skills = skills or []
        
        # Setup Jinja2 Environment
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build(self, config: RunnableConfig) -> str:
        """
        Builds the system prompt for the Operator Agent via Jinja2.
        """
        user_lang = SystemConfigService.get_language_preference()
        tree = self.context.get("project_structure", "")

        execution_ticket = self.state.get("execution_ticket", {}) or {}
        ticket_type = execution_ticket.get("ticket_type", "task").lower()

        # 1. Project Structure Section
        non_fs_tasks = ["web_research", "wiki_update", "dynamic_task", "knowledge_harvesting", "data_analysis"]
        if ticket_type in non_fs_tasks:
            tree_section = "- Project Structure: [Omitted for Non-Filesystem Task]"
        else:
            tree_section = f"- Project Structure:\n{tree}"

        # 2. Subconscious Context Hydration (EvoContext)
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        # 3. Prepare Template Context
        template_vars = {
            "user_lang": user_lang,
            "tree_section": tree_section,
            "environment": {
                "summaries": ctx.environment_summaries,
                "memory_replay": ctx.memory_replay,
                "boundaries": ctx.active_boundaries,
                "spatial_awareness": ctx.spatial_awareness,
                "user_preferences": ctx.metadata.get("user_preferences", {}),
                "mcp_inventory": tool_manager.get_mcp_inventory(),
            },
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw"),
                "core_raw": ctx.metadata.get("core_memory_raw"),
            },
            "blackboard": {
                "ticket": execution_ticket,
                "verification": self.state.get("verification_status"),
                "route_reason": self.state.get("scratchpad", {}).get("route_reason"),
            },
            "skills": [
                {
                    "name": s.get("name") if isinstance(s, dict) else getattr(s, "name", "Unknown"),
                    "description": s.get("description") if isinstance(s, dict) else getattr(s, "description", ""),
                }
                for s in self.skills
            ],
            "clipboard": self.state.get("scratchpad", {}).get("workspace_clipboard", []),
            "mcp_inventory": tool_manager.get_mcp_inventory(),
        }

        try:
            template = self.env.get_template("operator.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering Operator template: {e}")
            # Fallback to a minimal message
            return f"You are the Operator. Error loading template: {e}"
