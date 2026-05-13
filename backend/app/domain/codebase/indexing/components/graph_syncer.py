"""
GraphSyncer: Handles graph database synchronization.
"""
import logging

from app.core.file.service import is_test_file
from app.domain.codebase.indexing.components.content_indexer import IndexedContent
from app.domain.codebase.indexing.components.file_preparer import PreparedFile
from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class GraphSyncer:
    """
    Syncs indexed content to graph database:
    - File nodes
    - CodeEntity nodes
    - Relation edges
    """

    async def sync(
        self,
        prepared: PreparedFile,
        indexed: IndexedContent,
        file_line_count: int,
        source_file_pg_id: int,
        entity_pg_ids: dict[str, int]
    ):
        """
        Sync file and its entities to graph.
        """
        try:
            driver = await get_graph_db()
            project_id = prepared.repo.project_id

            # 1. Sync File node
            await driver.upsert_node("File", "path", {
                "path": prepared.rel_path,
                "project_id": project_id,
                "lines": file_line_count,
                "is_test": is_test_file(prepared.file_path),
                "pg_id": source_file_pg_id
            })

            # 2. Sync Entities and link to File
            for ent in indexed.entities:
                await driver.upsert_node("CodeEntity", "full_name", {
                    "full_name": ent.full_name,
                    "project_id": project_id,
                    "name": ent.name,
                    "type": ent.type,
                    "start_line": ent.start_line,
                    "end_line": ent.end_line,
                    "pg_id": entity_pg_ids.get(ent.full_name)
                })
                
                # Link File -> CONTAINS -> CodeEntity
                await driver.link_nodes(
                    "File", {"path": prepared.rel_path, "project_id": project_id},
                    "CodeEntity", {"full_name": ent.full_name, "project_id": project_id},
                    "CONTAINS"
                )

            # 3. Sync Relations (Entity -> RELATION -> Entity)
            for rel in indexed.relations:
                if not rel.target_full_name:
                    continue

                await driver.link_nodes(
                    "CodeEntity", {"full_name": rel.source_full_name, "project_id": project_id},
                    "CodeEntity", {"full_name": rel.target_full_name, "project_id": project_id},
                    "RELATION",
                    rel_props={"type": rel.relation_type}
                )

        except Exception as e:
            logger.warning(f"Graph Sync Failed for {prepared.rel_path}: {e}")
