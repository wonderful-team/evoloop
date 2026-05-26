"""
Checkpointer 持久化等价验证 (Phase 8)

验证 LangGraph checkpointer 在 EMBEDDED_MODE=true (SQLite)
和 EMBEDDED_MODE=false (PostgreSQL) 两种模式下都能正确保存、
加载和列 checkpoint。

SQLite 部分无条件运行；PostgreSQL 部分需 Docker Compose 启动 db 服务。
"""

import socket
import tempfile
from unittest.mock import patch

import pytest

from app.core.config import settings


def _service_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


POSTGRES_AVAILABLE = _service_available("localhost", 5432)
POSTGRES_SKIP = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")


# ═══════════════════════════════════════════════════════════════════
# EMBEDDED_MODE=true: SQLite Checkpointer
# ═══════════════════════════════════════════════════════════════════

class TestSqliteCheckpointer:
    """验证 SQLite checkpointer 在嵌入式模式下的持久化能力。"""

    @pytest.fixture
    async def sqlite_checkpointer(self):
        import aiosqlite
        from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        conn = await aiosqlite.connect(db_path)
        cp = FixedAsyncSqliteSaver(conn=conn)
        await cp.setup()
        yield cp
        await conn.close()

    def _make_config(self, thread_id: str) -> dict:
        """构建符合 LangGraph 要求的 config 结构。"""
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

    def _make_checkpoint(self, ts: str) -> dict:
        """构建符合 LangGraph 要求的 checkpoint 结构。"""
        import uuid
        return {
            "v": 1,
            "id": str(uuid.uuid4()),
            "ts": ts,
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        }

    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self, sqlite_checkpointer):
        """保存 checkpoint 后能正确加载。"""
        config = self._make_config("test-thread")
        checkpoint = self._make_checkpoint("2024-01-01T00:00:00Z")

        await sqlite_checkpointer.aput(config, checkpoint, {}, {})
        loaded = await sqlite_checkpointer.aget_tuple(config)

        assert loaded is not None
        assert loaded.checkpoint["ts"] == checkpoint["ts"]

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, sqlite_checkpointer):
        """能列出指定 thread 的所有 checkpoint。"""
        config = self._make_config("list-thread")
        for i in range(3):
            await sqlite_checkpointer.aput(
                config,
                self._make_checkpoint(f"2024-01-0{i+1}T00:00:00Z"),
                {},
                {},
            )

        checkpoints = [c async for c in sqlite_checkpointer.alist(config)]
        assert len(checkpoints) == 3

    @pytest.mark.asyncio
    async def test_checkpoint_metadata_preserved(self, sqlite_checkpointer):
        """checkpoint 的 metadata 应被正确保存。"""
        config = self._make_config("meta-thread")
        checkpoint = self._make_checkpoint("2024-01-01T00:00:00Z")
        metadata = {"run_id": "run_001", "status": "completed"}

        await sqlite_checkpointer.aput(config, checkpoint, metadata, {})
        loaded = await sqlite_checkpointer.aget_tuple(config)

        assert loaded.metadata == metadata

    @pytest.mark.asyncio
    async def test_delete_thread(self, sqlite_checkpointer):
        """删除 thread 后 checkpoint 应不可访问。"""
        config = self._make_config("del-thread")
        await sqlite_checkpointer.aput(
            config,
            self._make_checkpoint("2024-01-01T00:00:00Z"),
            {},
            {},
        )

        pre = await sqlite_checkpointer.aget_tuple(config)
        assert pre is not None

        # adelete_thread takes thread_id (str), not config dict
        await sqlite_checkpointer.adelete_thread(config["configurable"]["thread_id"])
        post = await sqlite_checkpointer.aget_tuple(config)
        assert post is None


# ═══════════════════════════════════════════════════════════════════
# EMBEDDED_MODE=false: PostgreSQL Checkpointer
# ═══════════════════════════════════════════════════════════════════

class TestPostgresCheckpointer:
    """验证 PostgreSQL checkpointer 在生产模式下的持久化能力。

    需要 PostgreSQL 容器运行：
        docker-compose up -d db
    """

    def _make_config(self, thread_id: str) -> dict:
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

    def _make_checkpoint(self, ts: str) -> dict:
        import uuid
        return {
            "v": 1,
            "id": str(uuid.uuid4()),
            "ts": ts,
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        }

    @POSTGRES_SKIP
    @pytest.fixture
    async def postgres_checkpointer(self):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        import psycopg

        conn = await psycopg.AsyncConnection.connect(
            "postgresql://postgres:admin888@localhost:5432/app",
            autocommit=True,
        )
        cp = AsyncPostgresSaver(conn)
        await cp.setup()
        yield cp
        await conn.close()

    @POSTGRES_SKIP
    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self, postgres_checkpointer):
        """与 SQLite 版本功能等价：保存后能正确加载。"""
        config = self._make_config("pg-test-thread")
        checkpoint = self._make_checkpoint("2024-06-01T00:00:00Z")

        await postgres_checkpointer.aput(config, checkpoint, {}, {})
        loaded = await postgres_checkpointer.aget_tuple(config)

        assert loaded is not None
        assert loaded.checkpoint["ts"] == checkpoint["ts"]

        # Cleanup
        await postgres_checkpointer.adelete_thread(config["configurable"]["thread_id"])

    @POSTGRES_SKIP
    @pytest.mark.asyncio
    async def test_list_checkpoints(self, postgres_checkpointer):
        """与 SQLite 版本功能等价：能列出 checkpoint。"""
        config = self._make_config("pg-list-thread")
        for i in range(3):
            await postgres_checkpointer.aput(
                config,
                self._make_checkpoint(f"2024-06-0{i+1}T00:00:00Z"),
                {},
                {},
            )

        checkpoints = [c async for c in postgres_checkpointer.alist(config)]
        assert len(checkpoints) == 3

        # Cleanup
        await postgres_checkpointer.adelete_thread(config["configurable"]["thread_id"])
