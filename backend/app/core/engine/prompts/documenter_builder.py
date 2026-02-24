import os
import logging
from jinja2 import Environment, FileSystemLoader
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class DocumenterPromptBuilder:
    """
    Builder for Documenter prompts via Jinja2.
    """
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build_architect_system_prompt(self, project_id: int, skills: list | None = None) -> str:
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        template_vars = {
            "project_id": project_id,
            "user_lang": SystemConfigService.get_language_preference(),
            "skills": skills or [],
            "environment": {
                "summaries": ctx.environment_summaries,
                "boundaries": ctx.active_boundaries,
            }
        }

        try:
            template = self.env.get_template("documenter.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering Documenter template: {e}")
            return f"You are the Documenter. Error loading template: {e}"
