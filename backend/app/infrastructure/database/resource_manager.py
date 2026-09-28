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
from weakref import WeakKeyDictionary

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, QueuePool
from sqlalchemy.util.concurrency import greenlet_spawn
from sqlmodel import SQLModel
from sqlmodel import create_engine as create_sync_engine

from app.core.config import settings
from app.infrastructure.constants import AGENT_ACTIVITY_EXTRA_COLUMNS
from app.infrastructure.database.guarded_session import LeakGuardAsyncSession
from app.infrastructure.database.pool_instrumentation import (
    install as install_pool_instrumentation,
)
from app.infrastructure.database.pool_leak_probe import maybe_install

logger = logging.getLogger(__name__)

_ASYNC_POOL_FINALIZE_PATCH_INSTALLED = False


def install_async_pool_finalize_patch() -> None:
    """Patch SQLAlchemy's pool finalizer to async-clean orphaned async fairies.

    Root cause: sqlalchemy/sqlalchemy#12710.  When an asyncio task is cancelled
    while a :class:`._ConnectionFairy` has been checked out of an async pool but
    not yet adopted by the caller, the fairy is garbage collected without ever
    being checked back in.  SQLAlchemy's default ``_finalize_fairy`` logs a
    warning and drops the connection for async dialects because it cannot run
    async IO from a synchronous GC callback.

    This patch intercepts that GC callback for async pools and schedules the
    connection close (and record checkin) on the running event loop, so the
    connection is returned to the pool instead of being leaked.  It preserves
    normal cancellation/timeout semantics for application code.

    .. todo::
        This is a workaround for sqlalchemy/sqlalchemy#12710. Remove this
        patch once upstream fixes the orphan fairy problem, or when we upgrade
        to a SQLAlchemy version that no longer exhibits the leak. When removing,
        delete ``install_async_pool_finalize_patch``,
        ``_ASYNC_POOL_FINALIZE_PATCH_INSTALLED``, and the call site in
        ``DatabaseResourceManager.initialize``.
    """
    global _ASYNC_POOL_FINALIZE_PATCH_INSTALLED
    if _ASYNC_POOL_FINALIZE_PATCH_INSTALLED:
        return

    import sqlalchemy.pool.base as pool_base

    original_finalize = pool_base._finalize_fairy

    async def _async_finalize_cleanup(
        connection_record: Any, dbapi_connection: Any
    ) -> None:
        """Close an orphaned async connection and return its record to the pool."""
        # StaticPool 守卫（2026-09-19 组合测试事故）：静态池的物理连接被全部
        # 借用方共享——finalize 一个泄漏 fairy 若物理 close，会杀死正在使用的
        # 活连接（测试 in-memory 库表现为断言中途 no-such-table/closed database）。
        # 只告警、不 close、不动 record；泄漏的 checkout 由 watchdog/重启兜底，
        # 与既有生产语义一致。
        _pool = getattr(connection_record, "_ConnectionRecord__pool", None)
        if _pool is not None and type(_pool).__name__ == "StaticPool":
            logger.warning(
                "[ResourceManager] abandoned async fairy on StaticPool connection "
                "not physically closed (shared connection); record=%r",
                connection_record,
            )
            return
        try:
            if dbapi_connection is not None:
                # aiosqlite/asyncpg close() implementations use await_only()
                # internally, so they must run inside a greenlet.
                await greenlet_spawn(dbapi_connection.close)
        except Exception:
            logger.exception("[ResourceManager] Failed to close orphaned async connection")
        finally:
            if connection_record is not None:
                try:
                    # The underlying connection is gone; clear it so the pool
                    # creates a new one on the next checkout.
                    connection_record.dbapi_connection = None
                    connection_record.fairy_ref = None
                    connection_record.checkin()
                except Exception:
                    logger.exception(
                        "[ResourceManager] Failed to check in orphaned connection record"
                    )

    def _patched_finalize_fairy(
        dbapi_connection,
        connection_record,
        pool,
        ref,
        echo,
        transaction_was_reset=False,
        fairy=None,
    ):
        is_gc_cleanup = ref is not None
        if is_gc_cleanup and getattr(pool, "_dialect", None) and pool._dialect.is_async:
            # _finalize_fairy is called from the weakref callback with
            # dbapi_connection=None. Reconstruct it so we can close it, but do
            # NOT mutate the parameter we will pass to original_finalize below.
            conn = dbapi_connection
            if conn is None and connection_record is not None:
                conn = connection_record.dbapi_connection

            if connection_record is not None and conn is not None:
                try:
                    loop = asyncio.get_running_loop()

                    def _schedule() -> None:
                        asyncio.create_task(
                            _async_finalize_cleanup(connection_record, conn),
                            name="async-pool-finalize-cleanup",
                        )

                    loop.call_soon_threadsafe(_schedule)
                    return
                except RuntimeError:
                    # No running event loop; fall back to the original warning.
                    pass

        return original_finalize(
            dbapi_connection,
            connection_record,
            pool,
            ref,
            echo,
            transaction_was_reset=transaction_was_reset,
            fairy=fairy,
        )

    pool_base._finalize_fairy = _patched_finalize_fairy
    _ASYNC_POOL_FINALIZE_PATCH_INSTALLED = True
    logger.info(
        "[ResourceManager] Installed async pool finalize patch (sqlalchemy#12710)"
    )


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
            # 键必须是 loop 对象而非 id(loop)：loop 被 GC 后地址会被新 loop
            # 复用（实测 2026-09-19：id 碰撞命中已 dispose 的旧引擎 →
            # "Cannot operate on a closed database"，并解释历史组合测试漂移）。
            # WeakKeyDictionary 令 loop 死亡即条目消失，杜绝复用与无界增长。
            cls._instance._engines: WeakKeyDictionary = WeakKeyDictionary()
            cls._instance._session_factories: WeakKeyDictionary = WeakKeyDictionary()
            cls._instance._sqlite_conns: WeakKeyDictionary = WeakKeyDictionary()
            cls._instance._vector_stores: WeakKeyDictionary = WeakKeyDictionary()
            cls._instance._tables_ensured = False
            cls._instance._task_queue_path = None
        return cls._instance

    def _current_loop(self) -> asyncio.AbstractEventLoop | None:
        """Return the currently running event loop, or None if none."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    @staticmethod
    def _setup_sqlite_pragmas(engine):
        """Enable SQLite WAL mode and a longer busy timeout on every new connection."""
        # async engines expose the underlying sync engine via .sync_engine;
        # the sync engine itself can be used directly.
        target_engine = getattr(engine, "sync_engine", engine)

        @event.listens_for(target_engine, "connect")
        def _on_connect(dbapi_conn, _):
            try:
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA busy_timeout=30000")
            except Exception as e:
                logger.warning(f"[ResourceManager] SQLite pragma setup failed: {e}", exc_info=True)

    @property
    def engine(self):
        """Return the async engine for the current event loop."""
        return self._engines.get(self._current_loop())

    @property
    def sync_engine(self):
        return self._sync_engine

    @property
    def session_factory(self):
        """Return the session factory for the current event loop."""
        return self._session_factories.get(self._current_loop())

    @property
    def is_ready(self) -> bool:
        """True when any engine has been initialized (sync or current-loop async)."""
        return self._sync_engine is not None or self.engine is not None

    def pool_status(self) -> dict[str, dict[str, int] | None]:
        """Return pool statistics for the current-loop async engine and sync engine."""
        from app.infrastructure.database.pool_instrumentation import pool_stats

        async_engine = self.engine
        return {
            "async": pool_stats(async_engine.sync_engine) if async_engine is not None else None,
            "sync": pool_stats(self._sync_engine) if self._sync_engine is not None else None,
        }

    @property
    def vector_store(self):
        """Return the vector store for the current event loop."""
        return self._vector_stores.get(self._current_loop())

    async def initialize(self, create_tables: bool = True):
        """Initialize all database resources (SQL, Vector).

        Args:
            create_tables: Whether to create tables if they don't exist.
        """
        loop = self._current_loop()
        if loop is None:
            raise RuntimeError(
                "DatabaseResourceManager.initialize() must be called from a running event loop"
            )

        with self._init_lock:
            if loop in self._engines:
                return

            logger.info(
                f"🚀 Initializing Unified Database System (EMBEDDED_MODE={settings.EMBEDDED_MODE}, loop={id(loop)})"
            )

            # 1. Initialize Engines (Async and Sync)
            db_uri = settings.SQLALCHEMY_DATABASE_URI
            sync_db_uri = (
                str(db_uri).replace("+aiosqlite", "").replace("+asyncpg", "")
            )  # Strip async drivers for sync engine

            # Ensure SQLite parent directory exists (SQLite cannot create intermediate dirs)
            if "sqlite" in sync_db_uri:
                db_file_path = sync_db_uri.replace("sqlite:///", "", 1)
                Path(db_file_path).parent.mkdir(parents=True, exist_ok=True)

            is_sqlite = "sqlite" in sync_db_uri
            if settings.EMBEDDED_MODE or is_sqlite:
                connect_args = {
                    "check_same_thread": False,
                    "timeout": 30,
                }
                engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    echo_pool=settings.DB_ECHO_POOL,
                    future=True,
                    poolclass=AsyncAdaptedQueuePool,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    pool_timeout=settings.DB_POOL_TIMEOUT,
                    pool_recycle=settings.DB_POOL_RECYCLE,
                    pool_pre_ping=True,
                    connect_args=connect_args,
                )
                self._setup_sqlite_pragmas(engine)
                if self._sync_engine is None:
                    self._sync_engine = create_sync_engine(
                        sync_db_uri,
                        poolclass=QueuePool,
                        pool_size=settings.DB_POOL_SIZE,
                        max_overflow=settings.DB_MAX_OVERFLOW,
                        pool_timeout=settings.DB_POOL_TIMEOUT,
                        pool_recycle=settings.DB_POOL_RECYCLE,
                        pool_pre_ping=True,
                        connect_args=connect_args,
                    )
                    self._setup_sqlite_pragmas(self._sync_engine)
            else:
                connect_args = {"connect_timeout": settings.DB_CONNECT_TIMEOUT}
                engine = create_async_engine(
                    db_uri,
                    echo=settings.DB_ECHO,
                    echo_pool=settings.DB_ECHO_POOL,
                    future=True,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    pool_timeout=settings.DB_POOL_TIMEOUT,
                    pool_recycle=settings.DB_POOL_RECYCLE,
                    connect_args=connect_args,
                )
                if self._sync_engine is None:
                    self._sync_engine = create_sync_engine(
                        sync_db_uri,
                        pool_size=settings.DB_POOL_SIZE,
                        max_overflow=settings.DB_MAX_OVERFLOW,
                        pool_timeout=settings.DB_POOL_TIMEOUT,
                        pool_recycle=settings.DB_POOL_RECYCLE,
                        connect_args=connect_args,
                    )

            self._engines[loop] = engine
            pool_class = type(engine.sync_engine.pool).__name__
            logger.info(
                f"[ResourceManager] SQL Engine: {db_uri} (pool={pool_class}, loop={id(loop)})"
            )
            maybe_install(engine)
            # TODO(sqlalchemy#12710): remove once upstream fixes orphan fairies.
            install_async_pool_finalize_patch()
            install_pool_instrumentation(engine.sync_engine, settings.DB_SLOW_CHECKOUT_THRESHOLD)
            if self._sync_engine is not None:
                install_pool_instrumentation(self._sync_engine, settings.DB_SLOW_CHECKOUT_THRESHOLD)

            self._session_factories[loop] = async_sessionmaker(
                bind=engine, class_=LeakGuardAsyncSession, expire_on_commit=False
            )

            # 2. Initialize Tables & Extensions (once globally)
            if create_tables and not self._tables_ensured:
                await self._ensure_tables_exist(engine)
                self._tables_ensured = True

            # 3. Vector Store Initialization
            from app.infrastructure.database.vector import get_vector_store

            self._vector_stores[loop] = get_vector_store()



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
            if conn.dialect.name == "postgresql":
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

        # create_all 对已存在的表不加新列。旧库按需 ALTER 补列（幂等）：
        # run_id（run_id 隔离修复）+ react 度量埋点列（llm_calls 等，§10.2.1 阶段 D）。
        # 新库 create_all 已含这些列，此处仅在旧库缺列时触发。
        try:
            async with engine.connect() as conn:
                cols = await conn.run_sync(
                    lambda c: {col["name"] for col in inspect(c).get_columns("agent_activities")}
                )
                missing = [
                    (name, ctype)
                    for name, ctype in AGENT_ACTIVITY_EXTRA_COLUMNS
                    if name not in cols
                ]
                for name, ctype in missing:
                    async with engine.begin() as conn2:
                        await conn2.execute(
                            text(f"ALTER TABLE agent_activities ADD COLUMN {name} {ctype}")
                        )
                        logger.info("[ResourceManager] Added agent_activities.%s column (schema fallback)", name)
        except Exception as e:  # noqa: BLE001
            logger.warning("[ResourceManager] Failed to ensure agent_activities schema: %s", e)

        logger.info("[ResourceManager] Tables and extensions verified")

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

        self._tables_ensured = False

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
            self._tables_ensured = False
            logger.info("🔌 Database resources closed and reset.")

    async def reset(self):
        """Alias for close() to match testing patterns."""
        await self.close()

    @property
    def writes_table(self) -> str:
        return "writes" if settings.EMBEDDED_MODE else "checkpoint_writes"

    @property
    def placeholder(self) -> str:
        return "?" if settings.EMBEDDED_MODE else "%s"

    async def run_pool_watchdog(self) -> None:
        """Self-heal the async pool when connections stay checked out too long.

        Client-abort cancellation paths can still strand a checked-out fairy
        in rare races that the shielded session close does not cover (task
        FINISHED yet fairy never returned). Left alone the pool drains to
        zero capacity and every API call times out for 30s each — the
        observed "API hangs while WS heartbeat is alive" state. When
        checkedout stays at the ceiling for ``_WATCHDOG_SUSTAINED_S``, rebuild
        the pool: the engine object stays valid and new checkouts recreate
        connections lazily, so the API recovers within one cycle.
        """
        sustained: float = 0.0
        ceiling = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW - 2
        while True:
            await asyncio.sleep(15)
            engine = self.engine
            if engine is None:
                continue
            pool = engine.sync_engine.pool
            try:
                checked_out = pool.checkedout()
            except Exception:
                logger.exception("[PoolWatchdog] failed to read pool status")
                continue
            if checked_out < ceiling:
                sustained = 0.0
                continue
            sustained += 15
            logger.warning(
                "[PoolWatchdog] pool saturated: checkedout=%d (ceiling %d) sustained %.0fs",
                checked_out,
                ceiling,
                sustained,
            )
            if sustained < 60:
                continue
            logger.error(
                "[PoolWatchdog] rebuilding async pool after sustained saturation "
                "(checkedout=%d); active operations on abandoned connections will fail fast",
                checked_out,
            )
            try:
                await engine.dispose()
            except Exception:
                logger.exception("[PoolWatchdog] engine.dispose failed")
            sustained = 0.0

    @property
    def task_queue_path(self) -> Path:
        """Get the path for the asynchronous task queue database."""
        if not self._task_queue_path:
            # Consistent with previous default but managed here
            self._task_queue_path = Path(settings.SQLITE_PATH).parent / "task_queue.db"
        return self._task_queue_path


# Global Instance
db_resource_manager = DatabaseResourceManager()
