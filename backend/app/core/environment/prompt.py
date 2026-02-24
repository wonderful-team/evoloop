"""
App Environment Prompt

Centralizes the logic for generating the "Awakening" section of the system prompt.
This ensures both the Supervisor and Skills share the same understanding of the environment.
"""
import logging
import os
from jinja2 import Environment, FileSystemLoader
from app.core.context.manager import ContextManager
from app.core.context.plugins import plugin_registry

logger = logging.getLogger(__name__)


class AppEnvironmentPrompt:
    """
    Generates the environment context string based on the current AwakenedState.
    """

    @staticmethod
    def build(messages: list[dict] = None) -> str:
        """
        Build the environment context string using Jinja2 fragments.
        """
        try:
            ctx = ContextManager.current()
            plugin_registry.hydrate_context(ctx)

            template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine", "prompts", "templates")
            env = Environment(loader=FileSystemLoader(template_dir))

            template_vars = {
                "environment": {
                    "summaries": ctx.environment_summaries,
                    "boundaries": ctx.active_boundaries,
                    "memory_replay": ctx.memory_replay,
                    "identity_rules": ctx.identity_rules,
                    "spatial_awareness": ctx.spatial_awareness,
                },
                "tips": True
            }

            template = env.get_template("awakening.prompt.j2")
            return template.render(**template_vars)

        except Exception as e:
            logger.error(f"Failed to build AppEnvironmentPrompt via Jinja2: {e}")
            return ""
