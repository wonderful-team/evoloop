"""
Bash Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class BashSemanticProvider(LanguageSemanticProvider):
    """Provider for Bash/Shell script analysis."""

    def get_language_name(self) -> str:
        return "bash"

    def get_api_query(self) -> str:
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        return []

    def get_structure_query(self) -> str:
        """
        Extract Bash functions.
        """
        return """
        (function_definition
          name: (word) @name
        ) @function
        """

    def get_imports_query(self) -> str:
        """
        Extract sourced files (source or .).
        """
        return """
        (command
          name: (command_name (word) @cmd)
          argument: (word) @module
          (#match? @cmd "^(source|\\.)$")
        ) @import
        """
