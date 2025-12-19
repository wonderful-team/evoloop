from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
from app.logging import logger

# Create Async Engine
engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=settings.DB_ECHO,
    future=True,
    pool_size=20,
    max_overflow=10
)

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
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()

# Alias for compatibility
get_db_session = session_scope
