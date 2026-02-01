"""
GraphSyncer: Handles Neo4j graph database synchronization.
"""
import logging

from app.core.file.service import is_test_file
from app.domain.codebase.indexing.components.content_indexer import IndexedContent
from app.domain.codebase.indexing.components.file_preparer import PreparedFile
from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class GraphSyncer:
    """
    Syncs indexed content to Neo4j graph database:
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
        Sync file and its entities to Neo4j.
        """
        try:
            driver = await get_graph_db()
            async with driver.session() as n4j:
                project_id = prepared.repo.project_id

                # Sync File node
                await n4j.run(
                    """
                    MERGE (f:File {path: $path, project_id: $pid})
                    SET f.lines = $lines, f.is_test = $is_test, f.updated_at = timestamp(), f.pg_id = $pg_id
                """,
                    path=prepared.rel_path,
                    pid=project_id,
                    lines=file_line_count,
                    is_test=is_test_file(prepared.file_path),
                    pg_id=source_file_pg_id,
                )

                # Sync Entities
                for ent in indexed.entities:
                    await n4j.run(
                        """
                        MERGE (e:CodeEntity {full_name: $fname, project_id: $pid})
                        SET e.name = $name, e.type = $type, e.start_line = $start, e.end_line = $end, e.pg_id = $pg_id
                        WITH e
                        MATCH (f:File {path: $fpath, project_id: $pid})
                        MERGE (f)-[:CONTAINS]->(e)
                    """,
                        fname=ent.full_name,
                        pid=project_id,
                        name=ent.name,
                        type=ent.type,
                        start=ent.start_line,
                        end=ent.end_line,
                        fpath=prepared.rel_path,
                        pg_id=entity_pg_ids.get(ent.full_name),
                    )

                # Sync Relations
                for rel in indexed.relations:
                    if not rel.target_full_name:
                        continue

                    await n4j.run(
                        """
                        MATCH (s:CodeEntity {full_name: $src_name, project_id: $pid})
                        MERGE (t:CodeEntity {full_name: $tgt_name, project_id: $pid})
                        MERGE (s)-[:RELATION {type: $rel_type}]->(t)
                    """,
                        src_name=rel.source_full_name,
                        tgt_name=rel.target_full_name,
                        pid=project_id,
                        rel_type=rel.relation_type,
                    )

        except Exception as e:
            logger.warning(f"Neo4j Sync Failed for {prepared.rel_path}: {e}")
