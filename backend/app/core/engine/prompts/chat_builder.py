import logging

from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

from .utils import read_project_profile

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

        # Read PROJECT.md if exists
        project_profile = read_project_profile(ctx.working_directory, "[ChatPrompt]")

        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "environment_block": ctx.environment_block,
            "project_profile": project_profile,
        }

        return render_template("core/engine/chat.prompt.j2", **template_vars)
