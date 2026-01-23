import asyncio
import os
import sys

# Add backend to path to allow imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.infrastructure.database.sql.database import engine, Base
from app.core.config import settings

# Import models to ensure they are registered with Base metadata
import app.infrastructure.database.sql.models.codebase
import app.infrastructure.database.sql.models.learning
import app.infrastructure.database.sql.models.system

async def fix_vector_dimensions():
    print(f"🚀 [EvoLoop] Fixing Vector Dimensions to {settings.EMBEDDING_DIMENSIONS}...")
    
    tables_to_fix = ["code_chunks", "learned_skills", "tools"]
    
    async with engine.begin() as conn:
        for table in tables_to_fix:
            print(f"--> Dropping table: {table}")
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
            
        print("--> Recreating tables with current dimensions...")
        # Re-create only the missing tables using SQLAlchemy Metadata
        # We wrap in a sync wrapper or use run_sync since metadata.create_all is typically sync
        def create_tables(sync_conn):
            # We filter metadata to only create the tables we just dropped
            target_metadata = Base.metadata
            target_metadata.create_all(sync_conn, tables=[
                target_metadata.tables[t] for t in tables_to_fix
            ])
            
        await conn.run_sync(create_tables)
        
    print("✅ Vector Storage Re-initialized successfully.")
    print("✨ Schema is now aligned with EMBEDDING_DIMENSIONS setting.")

if __name__ == "__main__":
    asyncio.run(fix_vector_dimensions())
