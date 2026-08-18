import logging
from typing import Any

from app.utils.template import render_template

logger = logging.getLogger(__name__)


class LearningPromptBuilder:
    """
    Constructs prompts for the Learning module using Jinja2 templates.

    This builder provides a centralized way to render learning-related prompts
    with consistent error handling and fallback mechanisms.
    """

    # Template name mapping for cleaner code
    TEMPLATES = {
        "skill_synthesis": "core/learning/skill_synthesis.prompt.j2",
        "macro_metadata_synthesis": "core/learning/macro_metadata_synthesis.prompt.j2",
        "multimodal_synthesis": "core/learning/multimodal_synthesis.prompt.j2",
        "multimodal_context": "core/learning/multimodal_task_context.j2",
        "synthesis_human": "core/learning/synthesis_human.prompt.j2",
    }

    def _render_with_fallback(
        self,
        template_key: str,
        vars: dict[str, Any],
        fallback_msg: str = "Error loading template",
    ) -> str:
        """
        Generic template rendering with error handling.

        Args:
            template_key: Key in TEMPLATES dict
            vars: Template variables
            fallback_msg: Message prefix for fallback response

        Returns:
            Rendered template string or fallback message
        """
        template_name = self.TEMPLATES.get(template_key, template_key)
        try:
            return render_template(template_name, **vars)
        except Exception as e:
            logger.exception(f"Error rendering {template_name}: {e}")
            return f"{fallback_msg}: {e}"

    def build_skill_synthesis_prompt(self, vars: dict[str, Any]) -> str:
        """Renders the skill synthesis prompt."""
        return self._render_with_fallback(
            "skill_synthesis", vars, "Error loading skill synthesis template"
        )

    def build_macro_metadata_synthesis_prompt(self, vars: dict[str, Any]) -> str:
        """Renders the macro metadata synthesis prompt."""
        return self._render_with_fallback(
            "macro_metadata_synthesis",
            vars,
            "Error loading macro metadata synthesis template",
        )

    def build_multimodal_synthesis_prompt(self, vars: dict[str, Any]) -> str:
        """Renders the multimodal skill synthesis prompt."""
        return self._render_with_fallback(
            "multimodal_synthesis", vars, "Error loading multimodal synthesis template"
        )

    def build_multimodal_context_prompt(self, vars: dict[str, Any]) -> str:
        """Renders the task context for multimodal synthesis."""
        return self._render_with_fallback(
            "multimodal_context", vars, "Error loading multimodal context template"
        )

    def build_synthesis_human_prompt(self, vars: dict[str, Any] | None = None) -> str:
        """Renders the human prompt for skill synthesis."""
        result = self._render_with_fallback(
            "synthesis_human", vars or {}, "Error loading synthesis human template"
        )
        # Special fallback for human prompt - provide a meaningful default
        if result.startswith("Error loading"):
            return "Please analyze the trace and generate the skill YAML."
        return result
