import logging

from app.utils import render_template
from .base_builder import BasePromptBuilder

logger = logging.getLogger(__name__)


class ChatPromptBuilder(BasePromptBuilder):
    """
    Builder for Chat node prompts via Jinja2.
    """

    def build(self) -> str:
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        project_profile = self.read_project_profile(ctx.working_directory, "[ChatPrompt]")

        sys_info = {
            "cwd": ctx.working_directory,
            "project_profile": project_profile
        }

        from app.infrastructure.config.service import SystemConfigService
        template_vars = {
            "user_lang": self.get_user_lang(),
            "environment_block": ctx.environment_block,
            "sys_info": sys_info,
            "project_id": ctx.project_id,
            "agent_name": SystemConfigService.get_value("AGENT_NAME", "EvoLoop"),
            "agent_company": SystemConfigService.get_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司"),
            "agent_website": SystemConfigService.get_value("AGENT_WEBSITE", "https://evoloop.cn"),
        }

        return render_template("core/engine/chat.prompt.j2", **template_vars)
