import json
import logging

from app.i18n.service import i18n
from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

logger = logging.getLogger(__name__)


class WikiBuilder:
    """
    Builder for Wiki Generation prompts via Jinja2.
    Co-located with WikiService in app/domain/wiki/.
    """

    def _get_target_lang(self) -> str:
        return SystemConfigService.get_language_preference()

    def build_structure_prompt(self, file_tree: str, readme: str) -> str:
        template_vars = {
            "mode": "structure",
            "file_tree": file_tree,
            "readme": readme,
            "target_lang": self._get_target_lang()
        }
        return self._render(template_vars)

    def build_content_prompt(self, page_title: str, relevant_files_content: str, relevant_file_paths: list[str]) -> str:
        template_vars = {
            "mode": "content",
            "page_title": page_title,
            "relevant_files_content": relevant_files_content,
            "relevant_file_paths": relevant_file_paths,
            "i18n_relevant_files": i18n.get("wiki.generated_content.relevant_files"),
            "i18n_files_used": i18n.get("wiki.generated_content.files_used"),
            "target_lang": self._get_target_lang()
        }
        return self._render(template_vars)

    def build_concept_extraction_prompt(self, page_title: str, page_content: str) -> str:
        template_vars = {
            "mode": "concepts",
            "page_title": page_title,
            "truncated_content": page_content[:6000],
            "target_lang": self._get_target_lang()
        }
        return self._render(template_vars)

    def build_validation_prompt(self, structure: dict, project_context: str = "") -> str:
        template_vars = {
            "mode": "validation",
            "structure_json": json.dumps(structure, ensure_ascii=False, indent=2),
            "project_context": project_context or "Analyze the structure to infer project type.",
            "target_lang": self._get_target_lang()
        }
        return self._render(template_vars)

    def _render(self, template_vars: dict) -> str:
        try:
            return render_template("wiki/wiki.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Wiki template: {e}")
            return f"Wiki template error: {e}"
