"""
Profile embedding performance: model loading, encode speed, and full-index
with EMBEDDING_ENABLED=true.

Usage:
    EMBEDDED_MODE=true EMBEDDING_ENABLED=true uv run python scripts/profile_embedding.py
"""

import asyncio
import logging
import os
import sys
import tempfile
import time

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Circumvent circular import
from unittest.mock import MagicMock
import app.core.project
if "app.core.project.sync_tasks" not in sys.modules:
    sys.modules["app.core.project.sync_tasks"] = MagicMock()

from contextlib import asynccontextmanager
from app.infrastructure.embeddings.local import LocalEmbedder
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database.sql.database import Base
from app.models import Repository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("profile_embedding")

EVOLOOP_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def test_encode_speed(embedder: LocalEmbedder):
    logger.info("=" * 50)
    logger.info("BENCHMARK: encode latency per batch")
    logger.info("=" * 50)

    samples_en = [
        "def foo(): pass",
        "class UserModel(Base): ...",
        "async def find_symbol_definition(self, symbol_name, project_id): ...",
    ]
    samples_zh = [
        "索引文件后 SQL 数据一致性回归测试",
        "验证 IndexingService.index_file 正确调用流水线组件",
        "当前索引性能如何？",
    ]

    for label, texts in [("English (3 texts)", samples_en), ("Chinese (3 texts)", samples_zh)]:
        await embedder.embed_documents(texts)  # warmup
        t0 = time.perf_counter()
        for _ in range(10):
            await embedder.embed_documents(texts)
        elapsed = time.perf_counter() - t0
        logger.info(f"  {label}: {elapsed/10:.4f}s/encode  ({elapsed:.2f}s ×10)")


async def test_batched_throughput(embedder: LocalEmbedder):
    logger.info("-" * 50)
    logger.info("BENCHMARK: batch size throughput")
    logger.info("-" * 50)

    text = "async def find_symbol_definition(self, symbol_name: str, project_id: int = None) -> list[dict]:"
    for bs in [1, 4, 16, 32, 64]:
        t0 = time.perf_counter()
        await embedder.embed_documents([text] * bs)
        elapsed = time.perf_counter() - t0
        logger.info(f"  batch={bs:3d}: {elapsed*1000:.1f}ms  ({bs/elapsed:.0f} texts/s)")


async def benchmark_index_full_flow():
    logger.info("=" * 50)
    logger.info("BENCHMARK: full index with embedding enabled")
    logger.info("=" * 50)

    tmp = tempfile.NamedTemporaryFile(suffix=".prof.db", delete=False)
    db_path = tmp.name
    tmp.close()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        repo = Repository(project_id=1, name="profile-test", url="local", local_path=EVOLOOP_PATH)
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id

    service = IndexingService()

    @asynccontextmanager
    async def _scope():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    service.session_factory = _scope

    target = os.path.join(EVOLOOP_PATH, "app/api")
    logger.info(f"  target: {target}")

    t0 = time.perf_counter()
    await service.index_repository(target, repo_id, force=True)
    total = time.perf_counter() - t0

    async with session_factory() as session:
        counts = {}
        for t in ["source_files", "code_chunks", "code_entities", "code_relations"]:
            r = await session.execute(sa_text(f"SELECT COUNT(*) FROM {t}"))
            counts[t] = r.scalar()
    logger.info(f"  total time: {total:.2f}s")
    logger.info(f"  rows:       {counts}")

    if os.path.exists(db_path):
        os.unlink(db_path)

    return total


async def main():
    logger.info(f"EMBEDDING_ENABLED={os.environ.get('EMBEDDING_ENABLED', 'not set')}")

    # 1. Load with fallback
    t0 = time.perf_counter()
    model_path = os.environ.get("LIGHTNING_EMBEDDING_MODEL", "")
    embedder = LocalEmbedder(model_path=model_path) if model_path else None
    if embedder is None:
        logger.error("Set LIGHTNING_EMBEDDING_MODEL to a GGUF path")
        return
    await embedder._get_model()
    load_time = time.perf_counter() - t0
    logger.info(f"Model: {embedder.model_path}, load: {load_time:.2f}s")

    # 2. Encode speed
    await test_encode_speed(embedder)

    # 3. Batched throughput
    await test_batched_throughput(embedder)

    # 4. Full index with embeddings
    await benchmark_index_full_flow()


if __name__ == "__main__":
    asyncio.run(main())
