import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Import all models
from app.infrastructure.database.sql.database import Base
from app.models import *
from app.models import config # Ensures SystemConfig (SQLModel) is loaded

async def init_db():
    # Use environment variables directly
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "admin888")
    server = os.getenv("POSTGRES_SERVER", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "app")
    
    db_url = f"postgresql+psycopg://{user}:{password}@{server}:{port}/{db}"
    print(f"Initializing database: {db_url}")
    
    engine = create_async_engine(db_url, echo=True)
    
    async with engine.begin() as conn:
        print("Dropping all tables...")
        # Drop Base (SQLAlchemy) tables
        await conn.run_sync(Base.metadata.drop_all)
        # Drop SQLModel tables
        await conn.run_sync(SQLModel.metadata.drop_all)
        
        print("Creating all tables...")
        # Create SQLModel tables (systemconfig etc)
        await conn.run_sync(SQLModel.metadata.create_all)
        # Create Base tables
        await conn.run_sync(Base.metadata.create_all)
    
    print("Schema initialized successfully (Hybrid: SQLModel + SQLAlchemy).")

if __name__ == "__main__":
    if "app" not in os.getenv("POSTGRES_DB", ""):
        print("WARNING: POSTGRES_DB does not contain 'test'. Confimed?")
        pass
        
    asyncio.run(init_db())
