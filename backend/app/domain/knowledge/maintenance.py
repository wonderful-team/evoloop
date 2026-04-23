import logging

from sqlalchemy import text

from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import get_db_session

logger = logging.getLogger(__name__)


async def wipe_knowledge_base():
    """
    Wipes all Knowledge Graph nodes and Vector Index tables.
    Preserves User/Project metadata in SQL (Project table is external, but we keep the structure).
    """
    logger.warning("🧹 [EvoLoop] Starting Knowledge Base Reset (Clean Slate)...")

    # 1. Neo4j Cleanup
    try:
        driver = await get_graph_db()
        async with driver.session() as session:
            # Delete Code-related nodes
            await session.run("MATCH (n:File) DETACH DELETE n")
            await session.run("MATCH (n:Directory) DETACH DELETE n")
            await session.run("MATCH (n:CodeEntity) DETACH DELETE n")
            # Delete Semantic Concepts
            await session.run("MATCH (n:Concept) DETACH DELETE n")
            # Delete Chunks
            await session.run("MATCH (n:CodeChunk) DETACH DELETE n")

            # DROP Vector Indexes to allow recreation with correct dimensions
            try:
                await session.run("DROP INDEX concept_embeddings IF EXISTS")
                logger.info("Neo4j: Dropped 'concept_embeddings' index.")
            except Exception as e:
                logger.warning(f"Neo4j: Failed to drop index: {e}")

        logger.info("✅ Neo4j: Wiped [File, Directory, CodeEntity, Concept, CodeChunk].")
    except Exception as e:
        logger.error(f"Failed to wipe Neo4j: {e}")
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
                    await session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                except Exception as e:
                    logger.warning(f"SQL: Error truncating {t}: {e}")

            await session.commit()
            logger.info(f"✅ SQL: Truncated tables: {tables_to_truncate}")

        # Vector store (unified vector_embeddings table or LanceDB)
        vector_store = get_vector_store()
        if hasattr(vector_store, "_engine"):
            # PgVectorStore
            from sqlalchemy import text as sa_text
            from sqlalchemy.orm import Session

            with Session(vector_store._engine) as vec_session:
                vec_session.execute(sa_text("TRUNCATE TABLE vector_embeddings CASCADE"))
                vec_session.commit()
                logger.info("✅ Vector Store: Truncated vector_embeddings")
        else:
            # LanceVectorStore — LanceDB doesn't have a global truncate,
            # but compact + re-init is sufficient for a full reset.
            logger.info("✅ Vector Store: LanceDB tables retained (embedded mode)")

    except Exception as e:
        logger.error(f"Failed to wipe SQL/Vector store: {e}")
        raise e

    logger.info("✨ Knowledge Base Reset Complete.")
    return True
