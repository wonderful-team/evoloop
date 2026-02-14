"""
C Language Semantic Provider
"""
from typing import Any
from .sem_provider import LanguageSemanticProvider


class CSemanticProvider(LanguageSemanticProvider):
    """Provider for C analysis."""

    def get_language_name(self) -> str:
        return "c"

    def get_api_query(self) -> str:
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        return []

    def get_structure_query(self) -> str:
        """
        Extract C structs and functions.
        """
        return """
            (function_definition
                declarator: (_) @name
            ) @function
            
            (struct_specifier
                (type_identifier) @name
            ) @class
        """

    def get_imports_query(self) -> str:
        """
        Extract preprocessor includes.
        """
        return """
            (preproc_include path: (string_literal) @module) @import
            (preproc_include path: (system_lib_string) @module) @import
        """
