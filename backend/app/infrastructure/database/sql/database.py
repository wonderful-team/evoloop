import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_db_engine():
    """Create database engine based on configuration (SQLite or PostgreSQL)."""
    db_uri = settings.SQLALCHEMY_DATABASE_URI

    if settings.EMBEDDED_MODE or db_uri.startswith("sqlite"):
        # SQLite configuration (embedded mode)
        logger.info(f"[Database] Using SQLite at {settings.SQLITE_PATH}")
        return create_async_engine(
            db_uri,
            echo=settings.DB_ECHO,
            future=True,
            # SQLite-specific: disable pool for single-file access
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL configuration (full mode)
        logger.info(f"[Database] Using PostgreSQL at {settings.POSTGRES_SERVER}")
        return create_async_engine(
            db_uri,
            echo=settings.DB_ECHO,
            future=True,
            pool_size=50,  # Increased for concurrent indexing
            max_overflow=100,  # Increased for burst capacity
        )


# Create Async Engine
engine = create_db_engine()

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
