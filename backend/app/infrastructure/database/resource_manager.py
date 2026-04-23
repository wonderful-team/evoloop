"""
Database Resource Manager
=========================

Centralized management of all database-related resources in EvoLoop,
including SQLAlchemy (Async), SQLModel (Sync), Raw PG/SQLite pools, and Vector stores.

Unified lifespan management for both EMBEDDED_MODE and Full Mode.
Handles Table Creation and Initial Data Seeding.
"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, create_engine as create_sync_engine

from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseResourceManager:
    """
    Singleton manager for all database resources.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            # Use threading.Lock instead of asyncio.Lock to avoid
            # "bound to a different event loop" errors when Huey worker
            # threads call initialize() concurrently with the main loop.
            cls._instance._init_lock = threading.Lock()
            cls._instance._engine = None  # Async Engine
            cls._instance._sync_engine = None  # Sync Engine
            cls._instance._session_factory = None
            cls._instance._db_pool = None  # Postgres pool
            cls._instance._sqlite_conn = None  # Shared SQLite connection
            cls._instance._checkpointer = None
            cls._instance._vector_store = None
            cls._instance._task_queue_path = None
        return cls._instance

    @property
    def engine(self):
        return self._engine

    @property
    def sync_engine(self):
        return self._sync_engine

    @property
    def session_factory(self):
        return self._session_factory

    @property
    def checkpointer(self):
        return self._checkpointer

    @property
    def vector_store(self):
        return self._vector_store

    @property
    def writes_table(self) -> str:
        """Get the localized table name for checkpoint writes."""
        return "writes" if settings.EMBEDDED_MODE else "checkpoint_writes"

    @property
    def placeholder(self) -> str:
        """Get the SQL parameter placeholder for the current database."""
        return "?" if settings.EMBEDDED_MODE else "%s"

    async def initialize(self, create_tables: bool = True, seed_data: bool = True):
        """Initialize all database resources (SQL, Checkpointer, Vector)."""
        with self._init_lock:
            if self._initialized:
                return

            logger.info(f"🚀 Initializing Unified Database System (EMBEDDED_MODE={settings.EMBEDDED_MODE})")

            # 1. Initialize Engines (Async and Sync)
            db_uri = settings.SQLALCHEMY_DATABASE_URI
            sync_db_uri = str(db_uri).replace("+aiosqlite", "").replace("+asyncpg",
                                                                        "")  # Strip async drivers for sync engine

            if settings.EMBEDDED_MODE:
                self._engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    future=True,
                    connect_args={"check_same_thread": False},
                )
                self._sync_engine = create_sync_engine(sync_db_uri, connect_args={"check_same_thread": False})
            else:
                self._engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    future=True,
                    pool_size=50,
                    max_overflow=100,
                )
                self._sync_engine = create_sync_engine(sync_db_uri)

            self._session_factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # 2. Initialize Tables & Extensions
            if create_tables:
                await self._ensure_tables_exist()

            # 3. Initialize Checkpointer Resources
            await self._init_checkpointer()

            # 4. Vector Store Initialization
            from app.infrastructure.database.vector import get_vector_store
            self._vector_store = get_vector_store()

            # 5. Seed Initial Data
            if seed_data:
                await self._seed_initial_data()

            self._initialized = True

    async def _ensure_tables_exist(self):
        """Execute metadata.create_all and handle extensions."""
        from app.infrastructure.database.sql.database import Base
        from app import models  # noqa: F401 - Register all models
        from app.domain.project.requirements import models as _req_models  # noqa: F401

        logger.info("[ResourceManager] Ensuring tables exist...")
        async with self._engine.begin() as conn:
            if not settings.EMBEDDED_MODE:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[ResourceManager] Tables and extensions verified")

    async def _init_checkpointer(self):
        """Initialize the appropriate LangGraph checkpointer."""
        if settings.EMBEDDED_MODE:
            import aiosqlite
            # AsyncSqliteSaver is imported inside FixedAsyncSqliteSaver's module

            db_uri_raw = settings.SQLALCHEMY_DATABASE_URI
            sqlite_path = db_uri_raw.replace("sqlite+aiosqlite:///", "").replace("sqlite://", "")

            self._sqlite_conn = await aiosqlite.connect(sqlite_path)
            # FIX: Use DELETE journal mode instead of WAL to prevent checkpoint loss.
            # WAL mode can cause intermittent write failures under certain conditions,
            # leading to missing checkpoints while messages continue to be saved.
            await self._sqlite_conn.execute("PRAGMA journal_mode=DELETE")
            await self._sqlite_conn.execute("PRAGMA busy_timeout=30000")
            await self._sqlite_conn.commit()
            from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver
            self._checkpointer = FixedAsyncSqliteSaver(conn=self._sqlite_conn)
            await self._checkpointer.setup()
            logger.info("[ResourceManager] SQLite checkpointer initialized (WAL mode, busy_timeout=30s)")
        else:
            from psycopg_pool import AsyncConnectionPool
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            self._db_pool = AsyncConnectionPool(
                conninfo=str(settings.SQLALCHEMY_DATABASE_URI).replace("+psycopg", ""),
                max_size=20,
                kwargs={"autocommit": True},
                open=False
            )
            await self._db_pool.open()
            self._checkpointer = AsyncPostgresSaver(self._db_pool)
            await self._checkpointer.setup()
            logger.info("[ResourceManager] Postgres checkpointer initialized")

    async def _seed_initial_data(self):
        """Trigger data seeding (initial_data.init)."""
        try:
            from app.initial_data import init as seed_init
            # Seed init usually uses the sync engine via app.core.db 
            # (which we are about to replace with a proxy to our sync_engine)
            await asyncio.to_thread(seed_init)
            logger.info("[ResourceManager] Initial data seeding complete")
        except Exception as e:
            logger.warning(f"[ResourceManager] Seeding failed (non-critical): {e}")

    async def shutdown(self):
        """Close all connections and pools."""
        logger.info("🔌 Shutting down Database Resources")

        # Close vector store
        if self._vector_store and hasattr(self._vector_store, "close"):
            self._vector_store.close()
            logger.info("[ResourceManager] Vector store closed")

        if self._engine:
            await self._engine.dispose()

        if self._db_pool:
            await self._db_pool.close()

        if self._sqlite_conn:
            await self._sqlite_conn.close()

        self._initialized = False

    @property
    def task_queue_path(self) -> Path:
        """Get the path for the asynchronous task queue database."""
        if not self._task_queue_path:
            # Consistent with previous default but managed here
            from app.core.config import settings
            self._task_queue_path = Path(settings.SQLITE_PATH).parent / "task_queue.db"
        return self._task_queue_path

    @asynccontextmanager
    async def get_raw_connection(self) -> AsyncGenerator[Any, None]:
        """Provides a raw database connection suitable for non-ORM SQL tasks."""
        if settings.EMBEDDED_MODE:
            import aiosqlite
            db_uri_raw = settings.SQLALCHEMY_DATABASE_URI
            sqlite_path = db_uri_raw.replace("sqlite+aiosqlite:///", "").replace("sqlite://", "")
            async with aiosqlite.connect(sqlite_path) as conn:
                await conn.execute("PRAGMA busy_timeout=30000")
                yield conn
        else:
            if not self._db_pool:
                raise RuntimeError("Postgres pool not initialized")
            async with self._db_pool.connection() as conn:
                yield conn


# Global Instance
db_resource_manager = DatabaseResourceManager()
