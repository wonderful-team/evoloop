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

    async def sync_to_graph(self, project_path: str, project_id: int, entities: list[DBTable]):
        """Sync database tables to graph.
        
        Args:
            project_path: 项目本地路径（用于获取项目级 graph driver）
            project_id: 项目 ID（用于图数据中的 project_id 属性）
            entities: DB table entities to sync
        """
        if not entities:
            return

        try:
            from app.infrastructure.database.graph.driver import GraphManager

            driver = GraphManager.get_driver(project_path=project_path)
            for t in entities:
                # 1. Upsert DBTable node
                await driver.upsert_node("DBTable", "name", {
                    "name": t.name,
                    "project_id": project_id,
                    "file": t.file_path
                })
                
                # 2. Sync Columns and link to Table
                for col_name in t.columns:
                    # c:DBColumn {name: col_name, table: $name, project_id: $pid}
                    await driver.upsert_node("DBColumn", "name", {
                        "name": col_name,
                        "table": t.name,
                        "project_id": project_id
                    })
                    
                    await driver.link_nodes(
                        "DBTable", {"name": t.name, "project_id": project_id},
                        "DBColumn", {"name": col_name, "project_id": project_id, "table": t.name},
                        "HAS_COLUMN"
                    )
        except Exception as e:
            logger.error(f"Graph Sync for DB failed: {e}")


db_extractor = DBExtractor()
