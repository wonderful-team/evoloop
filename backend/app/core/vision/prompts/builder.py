import logging

from app.infrastructure.config.service import SystemConfigService
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class VisionPromptBuilder:
    """
    Builder for Vision-related prompts via Jinja2.
    """

    def build(self) -> str:
        """Fallback implementation returning UI analysis prompt."""
        return self.build_ui_analysis_prompt()

    def get_user_lang(self) -> str:
        """Helper to get user's language preference."""
        return SystemConfigService.get_language_preference()

    def build_ui_analysis_prompt(self) -> str:
        template_vars = {
            "mode": "ui_analysis",
            "user_lang": self.get_user_lang()
        }
        return self._render(template_vars)

    def build_locate_element_prompt(self, element: str) -> str:
        template_vars = {
            "mode": "locate",
            "element": element,
            "user_lang": self.get_user_lang(),
        }
        return self._render(template_vars)

    def build_compare_screenshots_prompt(self, focus_instruction: str = "") -> str:
        template_vars = {
            "mode": "compare",
            "focus_instruction": focus_instruction,
            "user_lang": self.get_user_lang(),
        }
        return self._render(template_vars)

    def build_extract_text_prompt(self, region_instruction: str = "") -> str:
        template_vars = {
            "mode": "extract",
            "region_instruction": region_instruction
        }
        return self._render(template_vars)

    def _render(self, template_vars: dict) -> str:
        return render_template("core/vision/vision.prompt.j2", **template_vars)
