
import asyncio
import os
import sys

# Add backend to path to allow imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import get_db_session
from sqlalchemy import text
from app.logging import logger

async def wipe_knowledge_base():
    print("🧹 [EvoLoop] Starting Knowledge Base Reset (Clean Slate)...")

    # 1. Neo4j Cleanup
    # We want to remove all Code knowledge + Concepts (Memory vectors)
    # But preserve User Preferences if possible? 
    # User said "indexes and vectors". Concepts are vectors.
    print("--> Connecting to Neo4j...")
    driver = await get_graph_db()
    async with driver.session() as session:
        # Delete Code-related nodes
        await session.run("MATCH (n:File) DETACH DELETE n")
        await session.run("MATCH (n:Directory) DETACH DELETE n")
        await session.run("MATCH (n:CodeEntity) DETACH DELETE n")
        # Delete Semantic Concepts
        await session.run("MATCH (n:Concept) DETACH DELETE n")
        # Delete Chunks? (Usually stored as properties or chunks but let's be safe)
        await session.run("MATCH (n:CodeChunk) DETACH DELETE n")
        
        print("✅ Neo4j: Wiped [File, Directory, CodeEntity, Concept, CodeChunk].")

        # 1.1 Drop Vector Indexes (To handle dimension changes)
        try:
             await session.run("DROP INDEX concept_embeddings IF EXISTS")
             await session.run("DROP INDEX code_embeddings IF EXISTS") 
             print("✅ Neo4j: Dropped Vector Indexes (will be recreated on startup).")
        except Exception as e:
             print(f"⚠️ Neo4j: Failed to drop indexes: {e}")


    # 2. Postgres Cleanup
    print("--> Connecting to Postgres...")
    async with get_db_session() as session:
        # Truncate tables with cascade
        # clearing source_files clears chunks, entities, relations via foreign keys usually, 
        # but TRUNCATE CASCADE makes it sure.
        
        tables_to_truncate = [
            "code_chunks", 
            "code_relations", 
            "code_entities", 
            "source_files",
            "repositories", 
            "tools" 
        ]
        
        for t in tables_to_truncate:
             try:
                 # Check if table exists first? Or just try truncate.
                 # Using CASCADE to handle FKs
                 await session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
             except Exception as e:
                 print(f"⚠️ Postgres: Error truncating {t} (might not exist): {e}")
        
        await session.commit()
        print(f"✅ Postgres: Truncated tables: {tables_to_truncate}")

    print("✨ Knowledge Base Reset Complete. System is ready for fresh indexing.")

if __name__ == "__main__":
    asyncio.run(wipe_knowledge_base())
