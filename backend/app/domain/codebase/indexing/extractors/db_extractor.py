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
        except Exception as e:
            logger.error(f"DB Extraction failed for {file_path}: {e}")
            return []

    async def sync_to_graph(self, project_id: int, tables: list[DBTable]):
        """Sync database tables to Neo4j graph."""
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
