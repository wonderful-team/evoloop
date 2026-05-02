import logging
import os

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

        # Read PROJECT.md if exists
        project_profile = ""
        if ctx.working_directory:
            profile_path = os.path.join(ctx.working_directory, "PROJECT.md")
            if os.path.isfile(profile_path):
                try:
                    from app.utils import file as file_utils
                    content = file_utils.read_file(profile_path)
                    project_profile = content
                except Exception as e:
                    logger.debug(f"[ChatPrompt] Failed to read PROJECT.md: {e}")

        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "environment_block": ctx.environment_block,
            "project_profile": project_profile,
        }

        return render_template("core/engine/chat.prompt.j2", **template_vars)
