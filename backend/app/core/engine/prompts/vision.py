import logging
from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

logger = logging.getLogger(__name__)


class VisionPromptBuilder:
    """
    Builder for Vision-related prompts via Jinja2.
    """

    def build_ui_analysis_prompt(self) -> str:
        template_vars = {
            "mode": "ui_analysis",
            "user_lang": SystemConfigService.get_language_preference()
        }
        return self._render(template_vars)

    def build_locate_element_prompt(self, element: str) -> str:
        template_vars = {
            "mode": "locate",
            "element": element,
            "user_lang": SystemConfigService.get_language_preference()
        }
        return self._render(template_vars)

    def build_compare_screenshots_prompt(self, focus_instruction: str = "") -> str:
        template_vars = {
            "mode": "compare",
            "focus_instruction": focus_instruction,
            "user_lang": SystemConfigService.get_language_preference()
        }
        return self._render(template_vars)

    def build_extract_text_prompt(self, region_instruction: str = "") -> str:
        template_vars = {
            "mode": "extract",
            "region_instruction": region_instruction
        }
        return self._render(template_vars)

    def _render(self, template_vars: dict) -> str:
        try:
            return render_template("vision/vision.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Vision template: {e}")
            return f"Error loading vision analysis prompt: {e}"
