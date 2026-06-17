import logging

from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import get_db_session

logger = logging.getLogger(__name__)


async def wipe_knowledge_base(project_path: str | None = None):
    """
    Wipes all Knowledge Graph nodes and Vector Index tables.
    Preserves User/Project metadata in SQL (Project table is external, but we keep the structure).
    
    Args:
        project_path: 项目本地路径。提供时只清理该项目的数据，None 时清理全局数据。
    """
    scope = f"project: {project_path}" if project_path else "global"
    logger.warning(f"🧹 [EvoLoop] Starting Knowledge Base Reset ({scope})...")

    # 1. Graph Cleanup
    try:
        driver = await get_graph_db(project_path=project_path)
        # Delete nodes via high-level API for cross-backend compatibility
        labels_to_delete = ["File", "Directory", "CodeEntity", "Concept", "Memory", "CodeChunk"]
        for label in labels_to_delete:
            count = await driver.delete_nodes(label)
            if count > 0:
                logger.info(f"Graph: Deleted {count} nodes of type {label}")

        # DROP Vector Indexes (Neo4j specific, we use execute_query which is intercepted/handled)
        try:
            await driver.execute_query("DROP INDEX concept_embeddings IF EXISTS")
            logger.info("Graph: Dropped 'concept_embeddings' index (if applicable).")
        except Exception as e:
            logger.warning(f"Graph: Failed to drop index: {e}")

        logger.info("✅ Graph: Wiped core knowledge nodes.")
    except Exception as e:
        logger.error(f"Failed to wipe graph: {e}")
        raise e

    # 2. SQL / Vector Store Cleanup
    try:
        from app.infrastructure.database.vector import get_vector_store

        async with get_db_session() as session:
            tables_to_truncate = [
                "code_chunks",
                "code_relations",
                "code_entities",
                "source_files",
                "tools",
            ]

            for t in tables_to_truncate:
                try:
                    if settings.EMBEDDED_MODE:
                        await session.execute(text(f"DELETE FROM {t};"))
                    else:
                        await session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                except Exception as e:
                    logger.warning(f"SQL: Error truncating {t}: {e}")

            logger.info(f"✅ SQL: Truncated tables: {tables_to_truncate}")

        # Vector store (per-project or global)
        vector_store = get_vector_store(project_path=project_path)
        vector_store.truncate_all()
        logger.info(f"✅ Vector Store: All data truncated ({scope})")

    except Exception as e:
        logger.error(f"Failed to wipe SQL/Vector store: {e}")
        raise e

    logger.info(f"✨ Knowledge Base Reset Complete ({scope}).")
    return True
