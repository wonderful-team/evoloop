import logging
from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

logger = logging.getLogger(__name__)


class ChatPromptBuilder:
    """
    Builder for Chat node prompts via Jinja2.
    """

    def build(self) -> str:
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "environment_block": ctx.environment_block,
        }

        try:
            return render_template("agents/chat.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Chat template: {e}")
            return "You are EvoLoop, a helpful AI assistant. (Error loading full template)"
