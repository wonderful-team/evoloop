import logging
import os
from dataclasses import dataclass

from app.constants import SEMANTIC_LANGUAGE_MAP
from app.utils.file import read_file_content

from .sem_provider import LanguageSemanticProvider

logger = logging.getLogger(__name__)


@dataclass
class DBTable:
    name: str
    file_path: str
    columns: list[str]


class DBExtractor:
    """
    Extracts Database Schema from code.
    Acts as a dispatcher to language-specific providers.
    """

    def __init__(self):
        # Use shared provider registry instead of creating own instances
        from .provider_registry import semantic_provider_registry
        self._registry = semantic_provider_registry

    def _get_provider(self, lang_name: str) -> LanguageSemanticProvider | None:
        """Get provider from shared registry."""
        return self._registry.get(lang_name)

    async def extract(self, file_path: str) -> list[DBTable]:
        ext = os.path.splitext(file_path)[1].lower()

        lang_name = None
        for name, exts in SEMANTIC_LANGUAGE_MAP.items():
            if ext in exts:
                lang_name = name
                break

        provider = self._get_provider(lang_name) if lang_name else None
        if not provider:
            return []

        try:
            content, _ = read_file_content(file_path)
            if not content:
                return []

            return provider.extract_db(file_path, content)
        except Exception as e:
            logger.error(f"DB Extraction failed for {file_path}: {e}")
            return []

db_extractor = DBExtractor()
