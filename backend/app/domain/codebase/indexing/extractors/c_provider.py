"""
C Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class CSemanticProvider(LanguageSemanticProvider):
    """Provider for C analysis."""

    def get_language_name(self) -> str:
        return "c"

    def get_api_query(self) -> str:
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        return []


