import asyncio
import logging
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.infrastructure.database.graph.driver import get_graph_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset_vectors():
    target_dim = settings.EMBEDDING_DIMENSIONS
    logger.info(f"STARTING VECTOR RESET. Target Dimension: {target_dim}")
    
    # 1. POSTGRES RESET
    logger.info("--- Postgres: Resetting Tables & Altering Columns ---")
    with Session(engine) as session:
        # Truncate tables with vector data
        # Cascade to handle dependencies (chunks, entities might be linked)
        # Note: Truncating code_chunks is safe as they are re-generated.
        # Tools: We can keep the tool definitions but clear the embeddings? 
        # Actually proper reset is to clear embeddings.
        
        logger.info("Truncating code_chunks...")
        try:
            session.exec(text("TRUNCATE TABLE code_chunks CASCADE"))
        except Exception as e:
            logger.warning(f"Failed to truncate code_chunks: {e}")

        # For Tools and Skills, we might want to keep the data but reset the vector column type.
        # Postgres `ALTER COLUMN ... TYPE ...` requires a conversion using `USING`.
        # Since we are changing dimension, the old data is invalid anyway.
        # We can set existing embeddings to NULL first.
        
        tables_with_vectors = ["code_chunks", "tools", "learned_skills"]
        
        for table in tables_with_vectors:
             logger.info(f"Processing table '{table}'...")
             
             # 1. Clear Data (Set to NULL)
             # This avoids conversion errors when changing dimension
             try:
                session.exec(text(f"UPDATE {table} SET embedding = NULL"))
                logger.info(f"  Scaled vectors to NULL in {table}")
             except Exception as e:
                 logger.warning(f"  Failed to clear vectors in {table}: {e}")
                 
             # 2. Alter Column Type
             # Explicit cast to the new dimension
             try:
                 alter_sql = f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({target_dim}) USING embedding::vector({target_dim})"
                 session.exec(text(alter_sql))
                 logger.info(f"  Altered {table}.embedding to vector({target_dim})")
             except Exception as e:
                 logger.error(f"  Failed to alter column in {table}: {e}")
                 
        session.commit()
        logger.info("Postgres reset and schema update complete.")

    # 2. NEO4J RESET
    logger.info("--- Neo4j: Resetting Indexes ---")
    driver = await get_graph_db()
    async with driver.session() as session:
        indexes = ["concept_embeddings", "episode_embeddings"]
        for idx in indexes:
            try:
                # Drop Index
                await session.run(f"DROP INDEX {idx} IF EXISTS")
                logger.info(f"Dropped index {idx}")
                
                # We also need to clear the embedding properties from nodes because they have wrong dim
                node_label = "Concept" if "concept" in idx else "Episode"
                await session.run(f"MATCH (n:{node_label}) SET n.embedding = NULL")
                logger.info(f"Cleared embedding property from {node_label} nodes")
                
                # Recreate Index
                create_query = f"""
                    CREATE VECTOR INDEX {idx} IF NOT EXISTS
                    FOR (n:{node_label})
                    ON (n.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {target_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """
                await session.run(create_query)
                logger.info(f"Recreated index {idx} with dim {target_dim}")
                
            except Exception as e:
                logger.error(f"Failed to process Neo4j index {idx}: {e}")
                
    # 3. RE-INDEXING TRIGGER
    # Codebase indexing runs in background. 
    # We might want to trigger it for active repositories?
    # For now, we leave it to the user to trigger "Refresh Index" or restart app.
    # The system is now in a consistent state to accept new data.
    
    logger.info("VECTOR RESET COMPLETE. Please restart the backend to ensure all connections use new schema.")

if __name__ == "__main__":
    asyncio.run(reset_vectors())
