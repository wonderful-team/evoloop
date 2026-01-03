import asyncio
from sqlalchemy import text
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import get_db_session
from app.logging import logger

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

    # 2. Postgres Cleanup (and Schema Sync)
    try:
        from app.domain.codebase.indexing.vectors.factory import EmbedderFactory

        # Resolve current dimension
        try:
            embedder = EmbedderFactory.get_embedder()
            # Probe dimension
            # We assume embed_query works. If it fails (no net), we might skip or default.
            # But "Reset" implies we want to be ready for indexing.
            dummy_vec = await embedder.embed_query("dim_check")
            target_dim = len(dummy_vec)
            logger.info(f"Target Embedding Dimension determined: {target_dim}")
        except Exception as e:
            logger.warning(f"Could not determine target dimension from Embedder (using defaults/skipping alter): {e}")
            target_dim = None

        async with get_db_session() as session:
            tables_to_truncate = [
                "code_chunks", 
                "code_relations", 
                "code_entities", 
                "source_files",
                "tools" 
            ]
            
            for t in tables_to_truncate:
                 try:
                     await session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                 except Exception as e:
                     logger.warning(f"Postgres: Error truncating {t}: {e}")
            
            # SCHEMA FIX: Adjust Vector Column Dimensions
            if target_dim:
                # We need to alter code_chunks and tools
                for table_name in ["code_chunks", "tools"]:
                    try:
                        # ALTER COLUMN TYPE requires dropping index/constraints sometimes if data exists,
                        # but we just truncated, so it should be fast and safe.
                        # Syntax: ALTER TABLE x ALTER COLUMN y TYPE vector(dim) USING ...
                        # Since empty, valid.
                        alter_query = f"ALTER TABLE {table_name} ALTER COLUMN embedding TYPE vector({target_dim});"
                        await session.execute(text(alter_query))
                        logger.info(f"Updated {table_name}.embedding to vector({target_dim})")
                    except Exception as e:
                        logger.error(f"Failed to alter {table_name} dimension: {e}")

            await session.commit()
            logger.info(f"✅ Postgres: Truncated tables & Synced Dimensions: {tables_to_truncate}")
    except Exception as e:
        logger.error(f"Failed to wipe Postgres: {e}")
        raise e

    logger.info("✨ Knowledge Base Reset Complete.")
    return True
