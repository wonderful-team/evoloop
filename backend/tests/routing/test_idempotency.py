import pytest

from app.core.routing import idempotency


@pytest.mark.asyncio
async def test_idempotency_dedup(monkeypatch):
    # Isolate the module-level dedupe table from other tests.
    monkeypatch.setattr(idempotency, "_seen", {})

    assert await idempotency.is_duplicate("m1", ttl=60) is False
    assert await idempotency.is_duplicate("m1", ttl=60) is True
    assert await idempotency.is_duplicate("m2", ttl=60) is False


@pytest.mark.asyncio
async def test_idempotency_empty_id():
    assert await idempotency.is_duplicate("") is False


@pytest.mark.asyncio
async def test_idempotency_expiry(monkeypatch):
    monkeypatch.setattr(idempotency, "_seen", {})
    # ttl=0 expires immediately, so the second call is treated as first-seen.
    assert await idempotency.is_duplicate("m3", ttl=0) is False
    assert await idempotency.is_duplicate("m3", ttl=0) is False
