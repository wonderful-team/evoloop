import os
import logging
from jinja2 import Environment, FileSystemLoader
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class ChatPromptBuilder:
    """
    Builder for Chat node prompts via Jinja2.
    """
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build(self) -> str:
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "environment": {
                "summaries": ctx.environment_summaries,
                "boundaries": ctx.active_boundaries,
                "memory_replay": ctx.memory_replay,
                "user_preferences": ctx.metadata.get("user_preferences", {}),
                "system_rules": ctx.metadata.get("system_rules", []),
            }
        }

        try:
            template = self.env.get_template("chat.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering Chat template: {e}")
            return "You are EvoLoop, a helpful AI assistant. (Error loading full template)"
