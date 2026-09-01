"""Integration tests for duplicate-method consolidation refactors.

These tests run in-process against the current source tree (no HTTP server),
so they exercise the code on disk regardless of any running service.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

# --- Test-scoped SQLite DB so DB-backed helpers are exercised for real. ---
# Set before importing any app module so `settings` picks up the test DB URI.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="evo_integration_"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"

os.environ.setdefault("SQLITE_PATH", str(_TEST_DB_PATH))
os.environ.setdefault("EMBEDDED_MODE", "true")


@pytest.fixture(scope="session")
def test_db_path() -> Path:
    return _TEST_DB_PATH


@pytest.fixture(scope="session")
def test_session_scope(test_db_path: Path):
    """A lightweight async session scope bound to the test SQLite DB.

    Mirrors ``app.infrastructure.database.session_scope`` but skips the global
    resource manager / vector-store initialization. Callers should
    monkeypatch the target module's ``session_scope`` with this fixture.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.infrastructure.database.sql.database import Base

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{test_db_path}",
        poolclass=None,  # NullPool: fresh connection per use (loop-safe)
    )

    async def _create_tables() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(_create_tables())

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _scope():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    yield _scope

    import asyncio

    asyncio.run(engine.dispose())
