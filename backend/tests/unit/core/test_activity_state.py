import asyncio
import logging

import pytest

from app.core.config import settings
from app.core.monitoring.activity_state import (
    _CANCELLATION_CACHE,
    _CANCELLATION_CACHE_LOCK,
    _CANCELLATION_LOCKS,
    ActivityStateService,
)
from app.logging import setup_logging


@pytest.fixture(autouse=True)
def reset_cancellation_cache():
    with _CANCELLATION_CACHE_LOCK:
        _CANCELLATION_CACHE.clear()
        _CANCELLATION_LOCKS.clear()
    yield
    with _CANCELLATION_CACHE_LOCK:
        _CANCELLATION_CACHE.clear()
        _CANCELLATION_LOCKS.clear()


class FakeResult:
    def scalar_one_or_none(self):
        return "running"


class FakeSession:
    def __init__(self):
        self.execute = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_check_cancellation_coalesces_concurrent_db_checks(monkeypatch):
    service = ActivityStateService()
    session = FakeSession()

    async def execute(*_args):
        await asyncio.sleep(0.01)
        return FakeResult()

    session.execute = execute
    monkeypatch.setattr(service, "_get_session_scope", lambda: lambda: session)

    results = await asyncio.gather(
        service.check_cancellation("thread-1"),
        service.check_cancellation("thread-1"),
    )

    assert results == [False, False]


@pytest.mark.asyncio
async def test_check_cancellation_uses_cached_result(monkeypatch):
    service = ActivityStateService()
    session = FakeSession()
    call_count = 0

    async def execute(*_args):
        nonlocal call_count
        call_count += 1
        return FakeResult()

    session.execute = execute
    monkeypatch.setattr(service, "_get_session_scope", lambda: lambda: session)

    assert await service.check_cancellation("thread-1") is False
    assert await service.check_cancellation("thread-1") is False
    assert call_count == 1


def test_db_driver_debug_logs_are_suppressed_even_in_debug_mode(monkeypatch):
    monkeypatch.setattr(settings, "LOG_LEVEL", "DEBUG")
    setup_logging()

    assert logging.getLogger("aiosqlite").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
