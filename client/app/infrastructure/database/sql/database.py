"""
SQLite database engine for EvoLoop Client.

PostgreSQL support has been moved to the server branch.
"""
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# SQLite async engine (client-only)
engine = create_async_engine(
    settings.DATABASE_URI,
    echo=settings.DB_ECHO,
    future=True,
    # SQLite-specific: disable pool for single-file access
    connect_args={"check_same_thread": False},
)
logger.info(f"[Database] Using SQLite at {settings.SQLITE_PATH}")

# Create Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# Base Model
class Base(DeclarativeBase):
    pass


# Dependency for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope():
    """
    Provide a transactional scope around a series of operations.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for compatibility
get_db_session = session_scope
