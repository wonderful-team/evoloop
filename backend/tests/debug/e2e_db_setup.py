"""
E2E 测试数据库初始化 —— 绕过 vector store（lancedb/pyarrow 架构不兼容）。
"""
import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine as create_sync_engine

from app.core.config import settings
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import Base

logger = logging.getLogger(__name__)

# 记录临时数据库文件路径，用于清理
_db_path: str | None = None


async def init_test_database():
    """初始化 SQLite 数据库（使用临时文件，所有连接共享），用于 E2E/集成测试。"""
    global _db_path
    # 使用临时文件而非 :memory:，确保 sync/async engine 共享同一个数据库
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp_db.name
    tmp_db.close()
    _db_path = db_path

    db_uri = f"sqlite+aiosqlite:///{db_path}"
    sync_db_uri = f"sqlite:///{db_path}"

    # 同步 settings，确保 CHECKPOINTER_DATABASE_URI 也指向同一个文件
    settings.SQLITE_PATH = db_path

    engine = create_async_engine(
        db_uri,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
    sync_engine = create_sync_engine(sync_db_uri, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Create tables
    from app import models  # noqa: F401 - Register all models
    from app.domain.project.requirements import models as _req_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    # Init checkpointer (使用同一个数据库文件，避免 :memory: 连接隔离)
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    sqlite_conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn=sqlite_conn)
    await checkpointer.setup()

    # Inject into singleton
    db_resource_manager._engine = engine
    db_resource_manager._sync_engine = sync_engine
    db_resource_manager._session_factory = session_factory
    db_resource_manager._sqlite_conn = sqlite_conn
    db_resource_manager._checkpointer = checkpointer
    db_resource_manager._initialized = True

    logger.info("[E2E] Test database initialized (SQLite in-memory)")
    return db_resource_manager


async def shutdown_test_database():
    """关闭测试数据库连接并删除临时文件。"""
    global _db_path
    if db_resource_manager._engine:
        await db_resource_manager._engine.dispose()
    if db_resource_manager._sqlite_conn:
        await db_resource_manager._sqlite_conn.close()
    db_resource_manager._initialized = False
    if _db_path and os.path.exists(_db_path):
        os.unlink(_db_path)
        _db_path = None
    logger.info("[E2E] Test database shut down")


@asynccontextmanager
async def test_db_session():
    """提供一个事务性测试 session，自动回滚。"""
    async with db_resource_manager.session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
