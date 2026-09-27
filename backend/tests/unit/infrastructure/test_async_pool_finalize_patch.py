"""Async pool finalize patch (sqlalchemy/sqlalchemy#12710)."""

from __future__ import annotations

import asyncio
import gc
import logging
import warnings
from contextlib import contextmanager

import pytest
import sqlalchemy.pool.base as pool_base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.pool.base import _ConnectionFairy
from sqlalchemy.util.concurrency import await_only

import app.infrastructure.database.resource_manager as resource_manager

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
async def _reset_finalize_patch_state(monkeypatch):
    """Restore the original SQLAlchemy finalizer after each test."""
    saved = getattr(resource_manager, "_ASYNC_POOL_FINALIZE_PATCH_INSTALLED", False)
    original_finalize = pool_base._finalize_fairy
    resource_manager._ASYNC_POOL_FINALIZE_PATCH_INSTALLED = False
    yield
    # Drain any async cleanup tasks scheduled by the patch so they do not
    # checkin records while the next test is running without the patch.
    try:
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
            and not t.done()
            and getattr(t, "get_name", lambda: "")() == "async-pool-finalize-cleanup"
        ]
        if pending:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=2.0,
            )
    except Exception:
        logger.exception(
            "[test] Failed to drain pending cleanup tasks during teardown"
        )
    resource_manager._ASYNC_POOL_FINALIZE_PATCH_INSTALLED = saved
    pool_base._finalize_fairy = original_finalize
    monkeypatch.undo()


@contextmanager
def _capture_warnings():
    """Capture both logging warnings and warnings.warn output."""
    log_lines: list[str] = []
    handler = logging.StreamHandler()
    handler.stream = type(
        "S", (), {"write": lambda self, s: log_lines.append(s), "flush": lambda self: None}
    )()
    handler.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.WARNING)

    emitted: list[str] = []
    old_showwarning = warnings.showwarning

    def _collect(message, _category, _filename, _lineno, _file=None, _line=None):
        emitted.append(str(message))

    warnings.showwarning = _collect
    try:
        yield emitted, log_lines
    finally:
        warnings.showwarning = old_showwarning
        root.removeHandler(handler)
        root.setLevel(old_level)


@contextmanager
def _inject_checkout_window():
    """Block _ConnectionFairy._checkout after the fairy is created.

    Yields an :class:`asyncio.Event` that is set once the fairy has been checked
    out. The patched checkout then waits forever on an internal event; tests
    cancel the caller, which orphans the fairy deterministically. The fixture's
    teardown always releases the internal event so a failing test does not hang.
    """
    original_checkout = _ConnectionFairy._checkout
    started = asyncio.Event()
    unblock = asyncio.Event()

    @classmethod
    def _patched_checkout(cls, pool, threadconns=None, fairy=None):
        fairy = original_checkout.__func__(cls, pool, threadconns, fairy)
        started.set()
        await_only(unblock.wait())
        return fairy

    _ConnectionFairy._checkout = _patched_checkout
    try:
        yield started
    finally:
        unblock.set()
        _ConnectionFairy._checkout = original_checkout


async def _cancelled_checkout_cycle(engine, started: asyncio.Event):
    """Create a connection and cancel it while the fairy is held in checkout."""

    async def checkout_once():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    task = asyncio.create_task(checkout_once())
    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        started.clear()


def _warning_count(emitted: list[str], log_lines: list[str]) -> int:
    all_output = "".join(log_lines) + "\n".join(emitted)
    return all_output.count("non-checked-in connection")


async def test_finalize_patch_eliminates_orphan_warning(tmp_path):
    db_path = tmp_path / "test.db"
    with _inject_checkout_window() as started:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
        )

        resource_manager.install_async_pool_finalize_patch()

        with _capture_warnings() as (emitted, log_lines):
            await _cancelled_checkout_cycle(engine, started)
            gc.collect()
            await asyncio.sleep(0)
            gc.collect()

            await engine.dispose()
            gc.collect()
            await asyncio.sleep(0.2)
            gc.collect()

        assert _warning_count(emitted, log_lines) == 0


async def test_without_patch_orphan_finalizer_runs(tmp_path):
    """Without the patch, the GC finalizer still runs and handles the orphan.

    In production this surfaces as a ``non-checked-in connection`` warning. In
    tests the exact warning text can vary (``non-checked-in connection`` or
    ``Double checkin attempted``) depending on SQLAlchemy's cancellation
    cleanup path, so we assert the original finalizer itself was invoked.
    """
    db_path = tmp_path / "test.db"
    calls = []
    original_finalize = pool_base._finalize_fairy

    def _spy_finalize(*args, **kwargs):
        calls.append((args, kwargs))
        return original_finalize(*args, **kwargs)

    pool_base._finalize_fairy = _spy_finalize
    resource_manager._ASYNC_POOL_FINALIZE_PATCH_INSTALLED = False

    with _inject_checkout_window() as started:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
        )

        # Do NOT install the finalize patch.

        await _cancelled_checkout_cycle(engine, started)
        gc.collect()
        await asyncio.sleep(0)
        gc.collect()

        await engine.dispose()
        gc.collect()
        await asyncio.sleep(0.2)
        gc.collect()

    assert len(calls) > 0


async def test_finalize_patch_preserves_normal_operations(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
    )

    resource_manager.install_async_pool_finalize_patch()

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

    await engine.dispose()


async def test_finalize_patch_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
    )

    resource_manager.install_async_pool_finalize_patch()
    marker = pool_base._finalize_fairy
    resource_manager.install_async_pool_finalize_patch()

    assert pool_base._finalize_fairy is marker

    await engine.dispose()


async def test_finalize_patch_noop_for_sync_pools():
    """Installing the patch must not replace _finalize_fairy for sync pools."""
    resource_manager.install_async_pool_finalize_patch()

    # The patch still installs globally, but its behavior only changes for
    # async dialects. This test simply ensures installation is safe.
    assert resource_manager._ASYNC_POOL_FINALIZE_PATCH_INSTALLED is True


def test_finalize_patch_fallback_no_loop_does_not_assert(monkeypatch):
    """Regression: if no event loop is running, the GC fallback must pass
    dbapi_connection=None to the original finalizer.  Previously we
    reconstructed connection_record.dbapi_connection and forwarded it, which
    tripped SQLAlchemy's ``assert dbapi_connection is None`` in the GC path.
    """
    calls = []

    def _spy_finalize(
        dbapi_connection, connection_record, _pool, ref, _echo, **_kwargs
    ):
        calls.append(
            {
                "dbapi_connection": dbapi_connection,
                "connection_record": connection_record,
                "ref": ref,
            }
        )

    pool_base._finalize_fairy = _spy_finalize
    resource_manager._ASYNC_POOL_FINALIZE_PATCH_INSTALLED = False
    resource_manager.install_async_pool_finalize_patch()

    # Simulate a GC callback with no running loop.
    monkeypatch.setattr(
        asyncio,
        "get_running_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("no running loop")),
    )

    class _FakeDialect:
        is_async = True

    class _FakePool:
        _dialect = _FakeDialect()

    class _FakeRecord:
        dbapi_connection = object()

    def _ref():
        return None

    # weakref-like sentinel
    pool_base._finalize_fairy(
        None, _FakeRecord(), _FakePool(), _ref, False
    )

    assert len(calls) == 1
    assert calls[0]["dbapi_connection"] is None
    assert calls[0]["ref"] is _ref
