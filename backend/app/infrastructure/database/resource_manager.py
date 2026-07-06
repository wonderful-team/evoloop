"""
Database Resource Manager
=========================

Centralized management of all database-related resources in EvoLoop,
including SQLAlchemy (Async), SQLModel (Sync), Raw PG/SQLite pools, and Vector stores.

Unified lifespan management for both EMBEDDED_MODE and Full Mode.
Handles Table Creation and Initial Data Seeding.

Thread-safety note:
    Huey runs worker threads with independent asyncio event loops. SQLAlchemy's
    async engine and aiosqlite connections are bound to the loop that created
    them, so this manager keeps a separate async engine / session factory
    per event loop. The synchronous engine is shared across threads.
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel import create_engine as create_sync_engine

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
            cls._instance._init_lock = threading.Lock()
            cls._instance._sync_engine = None  # Sync Engine (shared across threads)

            # Per-event-loop async resources. asyncio objects are bound to the
            # loop that created them; sharing them between Huey worker threads
            # causes "bound to a different event loop" errors.
            cls._instance._engines: dict[int, Any] = {}
            cls._instance._session_factories: dict[int, Any] = {}
            cls._instance._sqlite_conns: dict[int, Any] = {}
            cls._instance._vector_stores: dict[int, Any] = {}
            cls._instance._initialized_loops: set[int] = set()
            cls._instance._tables_ensured = False
            cls._instance._seeded = False
            cls._instance._task_queue_path = None
        return cls._instance

    def _current_loop_id(self) -> int:
        """Return the id of the currently running event loop, or -1 if none."""
        try:
            return id(asyncio.get_running_loop())
        except RuntimeError:
            return -1

    @property
    def engine(self):
        """Return the async engine for the current event loop."""
        return self._engines.get(self._current_loop_id())

    @property
    def sync_engine(self):
        return self._sync_engine

    @property
    def session_factory(self):
        """Return the session factory for the current event loop."""
        return self._session_factories.get(self._current_loop_id())

    @property
    def vector_store(self):
        """Return the vector store for the current event loop."""
        return self._vector_stores.get(self._current_loop_id())

    async def initialize(self, create_tables: bool = True, seed_data: bool = True):
        """Initialize all database resources (SQL, Vector)."""
        loop_id = self._current_loop_id()
        if loop_id == -1:
            raise RuntimeError(
                "DatabaseResourceManager.initialize() must be called from a running event loop"
            )

        with self._init_lock:
            if loop_id in self._initialized_loops:
                return

            logger.info(
                f"🚀 Initializing Unified Database System (EMBEDDED_MODE={settings.EMBEDDED_MODE}, loop={loop_id})"
            )

            # 1. Initialize Engines (Async and Sync)
            db_uri = settings.SQLALCHEMY_DATABASE_URI
            sync_db_uri = (
                str(db_uri).replace("+aiosqlite", "").replace("+asyncpg", "")
            )  # Strip async drivers for sync engine

            if settings.EMBEDDED_MODE:
                engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    future=True,
                    poolclass=NullPool,
                    connect_args={"check_same_thread": False},
                )
                if self._sync_engine is None:
                    self._sync_engine = create_sync_engine(
                        sync_db_uri,
                        poolclass=NullPool,
                        connect_args={"check_same_thread": False},
                    )
            else:
                engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    future=True,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
                )
                if self._sync_engine is None:
                    self._sync_engine = create_sync_engine(
                        sync_db_uri,
                        pool_size=settings.DB_POOL_SIZE,
                        max_overflow=settings.DB_MAX_OVERFLOW,
                        connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
                    )

            self._engines[loop_id] = engine
            pool_class = type(engine.sync_engine.pool).__name__
            logger.info(
                f"[ResourceManager] SQL Engine: {db_uri} (pool={pool_class}, loop={loop_id})"
            )

            self._session_factories[loop_id] = async_sessionmaker(
                bind=engine, class_=AsyncSession, expire_on_commit=False
            )

            # 2. Initialize Tables & Extensions (once globally)
            if create_tables and not self._tables_ensured:
                await self._ensure_tables_exist(engine)
                self._tables_ensured = True

            # 3. Vector Store Initialization
            from app.infrastructure.database.vector import get_vector_store

            self._vector_stores[loop_id] = get_vector_store()

            # 4. Seed Initial Data (once globally)
            if seed_data and not self._seeded:
                await self._seed_initial_data()
                self._seeded = True

            self._initialized_loops.add(loop_id)

    async def _ensure_tables_exist(self, engine):
        """Execute metadata.create_all and handle extensions."""
        from app.infrastructure.database.sql.database import Base
        from app.models import (  # noqa: F401
            codebase,
            conversation,
            learning,
            memory,
        )

        logger.info("[ResourceManager] Ensuring tables exist...")
        async with engine.begin() as conn:
            if not settings.EMBEDDED_MODE:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.info("[ResourceManager] Tables and extensions verified")

    async def _seed_initial_data(self):
        """Trigger data seeding (initial_data.init)."""
        try:
            from app.initial_data import init as seed_init

            # Seed init usually uses the sync engine via app.core.db
            # (which we are about to replace with a proxy to our sync_engine)
            await asyncio.to_thread(seed_init)
            logger.info("[ResourceManager] Initial data seeding complete")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ResourceManager] Seeding failed (non-critical): {e}")

    async def shutdown(self):
        """Close all connections and pools."""
        logger.info("🔌 Shutting down Database Resources")

        # Close vector stores
        for vs in self._vector_stores.values():
            if vs and hasattr(vs, "close"):
                vs.close()
        self._vector_stores.clear()
        logger.info("[ResourceManager] Vector stores closed")

        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._session_factories.clear()

        if self._sync_engine:
            self._sync_engine.dispose()
            self._sync_engine = None

        for conn in self._sqlite_conns.values():
            await conn.close()
        self._sqlite_conns.clear()

        self._initialized_loops.clear()
        self._tables_ensured = False
        self._seeded = False

    async def close(self):
        """Close all database resources."""
        with self._init_lock:
            for engine in self._engines.values():
                await engine.dispose()
            self._engines.clear()
            self._session_factories.clear()

            if self._sync_engine:
                self._sync_engine.dispose()
                self._sync_engine = None

            for conn in self._sqlite_conns.values():
                await conn.close()
            self._sqlite_conns.clear()

            self._vector_stores.clear()
            self._initialized_loops.clear()
            self._tables_ensured = False
            self._seeded = False
            logger.info("🔌 Database resources closed and reset.")

    async def reset(self):
        """Alias for close() to match testing patterns."""
        await self.close()

    @property
    def task_queue_path(self) -> Path:
        """Get the path for the asynchronous task queue database."""
        if not self._task_queue_path:
            # Consistent with previous default but managed here
            from app.core.config import settings

            self._task_queue_path = Path(settings.SQLITE_PATH).parent / "task_queue.db"
        return self._task_queue_path



# Global Instance
db_resource_manager = DatabaseResourceManager()
