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

    async def sync_to_graph(self, project_id: int, tables: list[DBTable]):
        if not tables:
            return
        try:
            from app.infrastructure.database.graph.driver import get_graph_db

            driver = await get_graph_db()
            async with driver.session() as session:
                for t in tables:
                    await session.run(
                        """
                        MERGE (t:DBTable {name: $name, project_id: $pid})
                        SET t.file = $file

                        WITH t
                        UNWIND $columns as col_name
                        MERGE (c:DBColumn {name: col_name, table: $name, project_id: $pid})
                        MERGE (t)-[:HAS_COLUMN]->(c)
                    """,
                        name=t.name,
                        pid=project_id,
                        file=t.file_path,
                        columns=t.columns,
                    )
        except Exception as e:
            logger.error(f"Graph Sync for DB failed: {e}")


db_extractor = DBExtractor()
