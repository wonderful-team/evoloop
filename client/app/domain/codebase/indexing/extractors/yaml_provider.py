"""
YAML Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class YamlSemanticProvider(LanguageSemanticProvider):
    """Provider for YAML configuration analysis."""

    def get_language_name(self) -> str:
        return "yaml"

    def get_api_query(self) -> str:
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        return []

    def get_structure_query(self) -> str:
        """
        Extract top-level YAML blocks as 'classes' to enable chunking.
        """
        return """
        (document
          (block_node
            (block_mapping
              (block_mapping_pair
                key: (_) @name
              ) @class
            )
          )
        )
        """

    def get_imports_query(self) -> str:
        return ""
