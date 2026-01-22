"""
Vue Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class VueSemanticProvider(LanguageSemanticProvider):
    """Provider for Vue.js Single File Component analysis."""

    def get_language_name(self) -> str:
        return "vue"

    def get_api_query(self) -> str:
        """
        Vue API calls (axios, fetch, etc.) - parsed from script section.
        Note: Vue uses HTML-like syntax, so we focus on script content.
        """
        return """
        ; API calls in script
        (call_expression
          function: (member_expression
            object: (identifier) @obj
            property: (property_identifier) @method)
          arguments: (arguments
            [(string) (template_string)] @path
          )
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        # Vue API parsing delegated to TSJSProvider for script content
        return []

    def get_structure_query(self) -> str:
        """
        Vue component structure extraction.
        Since Vue files are parsed as HTML, we extract key elements.
        """
        return """
        ; Vue script content (treated as JS)
        (script_element
          (raw_text) @script.content
        )

        ; Vue template content
        (template_element
          (raw_text) @template.content
        )

        ; Directives
        (directive_attribute
          (directive_name) @directive.name
        )

        ; Components (in template)
        (element
          (start_tag
            (tag_name) @component.name
          )
        )
        """

    def get_imports_query(self) -> str:
        return """
        ; Import statements in script
        (import_statement
          source: (string) @import.source
        )
        """
