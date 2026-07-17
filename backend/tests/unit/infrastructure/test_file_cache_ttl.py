"""TTL semantics for the embedded-mode FileCache.

Regression: setex/set(ex=...)/expire used to silently ignore TTL, leaving
stale entries (e.g. member benefits) forever in embedded mode."""

import asyncio
import json
import time

import pytest

from app.infrastructure.cache.file._core import _TTL_MARKER, FileCacheCore


@pytest.fixture
def fc(tmp_path):
    return FileCacheCore(cache_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_setex_expires(fc):
    await fc.setex("k", 1, "v")
    assert await fc.get("k") == "v"
    await asyncio.sleep(1.05)
    assert await fc.get("k") is None
    assert not await fc.exists("k")


@pytest.mark.asyncio
async def test_set_with_ex_expires(fc):
    await fc.set("k", "v", ex=1)
    assert await fc.get("k") == "v"
    await asyncio.sleep(1.05)
    assert await fc.get("k") is None


@pytest.mark.asyncio
async def test_set_without_ttl_is_permanent(fc):
    await fc.set("k", "v")
    await asyncio.sleep(0.05)
    assert await fc.get("k") == "v"


@pytest.mark.asyncio
async def test_expire_sets_ttl(fc):
    await fc.set("k", "v")
    assert await fc.expire("k", 1) is True
    assert await fc.get("k") == "v"
    await asyncio.sleep(1.05)
    assert await fc.get("k") is None


@pytest.mark.asyncio
async def test_expire_missing_key_returns_false(fc):
    assert await fc.expire("nope", 10) is False


@pytest.mark.asyncio
async def test_incr_preserves_ttl(fc, tmp_path):
    await fc.setex("counter", 100, 1)
    assert await fc.incr("counter") == 2
    # TTL envelope must survive the read-modify-write
    path = tmp_path / "strings" / "counter.json"
    raw = json.loads(path.read_text())
    assert _TTL_MARKER in raw
    assert raw["value"] == 2
    assert raw[_TTL_MARKER] > time.time() + 90


@pytest.mark.asyncio
async def test_legacy_raw_value_still_readable(fc, tmp_path):
    """Files written by older versions (raw value, no envelope) must still
    load and never expire."""
    path = tmp_path / "strings" / "legacy.json"
    path.write_text(json.dumps({"some": "dict"}))
    assert await fc.get("legacy") == {"some": "dict"}
