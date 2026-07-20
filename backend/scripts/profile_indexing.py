"""
Profile indexing performance against the evoloop codebase itself.

Usage:
    EMBEDDED_MODE=true uv run python scripts/profile_indexing.py
"""

import asyncio
import logging
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Circumvent circular import: sync_tasks.py imports IndexingService at
# module level. Pre-stuff a mock so the import chain doesn't re-enter service.py.
import app.core.project
if "app.core.project.sync_tasks" not in sys.modules:
    sys.modules["app.core.project.sync_tasks"] = MagicMock()

from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database.sql.database import Base
from app.models import Repository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("profile_indexing")


async def count_rows(session: AsyncSession):
    counts = {}
    for table in ["source_files", "code_chunks", "code_entities", "code_relations"]:
        result = await session.execute(sa_text(f"SELECT COUNT(*) FROM {table}"))
        counts[table] = result.scalar()
    return counts


EVOLOOP_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIRS = [
    "app/core",
    "app/domain",
    "app/infrastructure",
    "app/api",
]


async def main():
    logger.info(f"evoloop path: {EVOLOOP_PATH}")

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
    logger.info(f"Database created: {db_path}")

    async with session_factory() as session:
        repo = Repository(
            project_id=1,
            name="evoloop-self",
            url="local",
            local_path=EVOLOOP_PATH,
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id
        logger.info(f"Repo ID: {repo_id}")

    service = IndexingService()

    @asynccontextmanager
    async def _commit_scope():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    service.session_factory = _commit_scope

    # ── Profile per-directory indexing ──
    for target in TARGET_DIRS:
        target_path = os.path.join(EVOLOOP_PATH, target)
        if not os.path.isdir(target_path):
            logger.warning(f"Skipping {target_path}: not a directory")
            continue

        t0 = time.perf_counter()
        await service.index_repository(target_path, repo_id, force=True)
        elapsed = time.perf_counter() - t0

        async with session_factory() as session:
            counts = await count_rows(session)
        logger.info(f"  ⏱  {target}: {elapsed:.2f}s → rows: {counts}")

    # ── Summary ──
    async with session_factory() as session:
        final_counts = await count_rows(session)

    logger.info("=" * 50)
    logger.info("FINAL TABLES")
    logger.info("=" * 50)
    for name, cnt in final_counts.items():
        logger.info(f"  {name}: {cnt}")

    if os.path.exists(db_path):
        os.unlink(db_path)
        logger.info(f"Cleaned up {db_path}")


if __name__ == "__main__":
    asyncio.run(main())
