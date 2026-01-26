"""
Vue Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class VueSemanticProvider(LanguageSemanticProvider):
    """Provider for Vue.js Single File Component analysis."""

    def get_language_name(self) -> str:
        return "vue"

    def get_api_query(self) -> str:
        # Currently we cannot parse JS inside Vue script blocks directly
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        # Vue API parsing delegated to TSJSProvider for script content
        return []

    def get_structure_query(self) -> str:
        """
        Vue component structure extraction.
        """
        return """
        ; Vue script content
        (script_element
          (text) @script.content
        )

        ; Vue template content
        (template_element
          (text) @template.content
        )

        ; Components (PascalCase only)
        (element
          (start_tag
            (tag_name) @component.name
          )
          (#match? @component.name "^[A-Z]")
        )
        """

    def get_imports_query(self) -> str:
        return ""
