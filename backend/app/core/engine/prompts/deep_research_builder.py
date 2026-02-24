import os
import logging
from jinja2 import Environment, FileSystemLoader
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class DeepResearchPromptBuilder:
    """
    Builder for Deep Research prompts, handling dynamic language injection via Jinja2.
    """
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def _get_common_vars(self):
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry
        
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)
        
        return {
            "user_lang": SystemConfigService.get_language_preference(),
            "environment": {
                "summaries": ctx.environment_summaries,
                "boundaries": ctx.active_boundaries,
                "memory_replay": ctx.memory_replay,
            }
        }

    def build_plan_prompt(self, context: str = "") -> str:
        template_vars = self._get_common_vars()
        template_vars.update({
            "mode": "plan",
            "research_context": context
        })
        return self._render(template_vars)

    def build_update_prompt(self, iteration: int) -> str:
        template_vars = self._get_common_vars()
        template_vars.update({
            "mode": "update",
            "iteration": iteration
        })
        return self._render(template_vars)

    def build_conclusion_prompt(self) -> str:
        template_vars = self._get_common_vars()
        template_vars.update({
            "mode": "conclusion"
        })
        return self._render(template_vars)

    def _render(self, template_vars: dict) -> str:
        try:
            template = self.env.get_template("deep_research.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering DeepResearch template: {e}")
            return f"You are the Deep Researcher. Error loading template: {e}"
