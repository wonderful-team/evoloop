"""
Database Extractor
==================

Extracts database schema definitions from code files.
"""
import logging

from app.domain.codebase.indexing.extractors.base_extractor import SemanticExtractorBase
from app.domain.codebase.schemas import DBTable

logger = logging.getLogger(__name__)


class DBExtractor(SemanticExtractorBase[DBTable]):
    """
    Extracts Database Schema from code.
    Acts as a dispatcher to language-specific providers.
    """

    async def extract(self, file_path: str) -> list[DBTable]:
        """Extract database tables from file."""
        # Detect language
        lang_name = self._detect_language(file_path)
        if not lang_name:
            return []

        # Get provider
        provider = self._get_provider(lang_name)
        if not provider:
            return []

        # Read file
        content = self._read_file(file_path)
        if not content:
            return []

        try:
            return provider.extract_db(file_path, content)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"DB Extraction failed for {file_path}: {e}")
            return []


db_extractor = DBExtractor()
