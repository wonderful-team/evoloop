"""
Tests for FileCache implementation.
"""
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import FileCacheCore for testing (standalone file-based cache implementation)
from app.infrastructure.cache.file import FileCacheCore as FileCache


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def file_cache(temp_cache_dir):
    """Create FileCache instance with temp directory."""
    cache = FileCache(cache_dir=temp_cache_dir)
    yield cache


class TestFileCacheBasics:
    """Test basic key-value operations."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, file_cache):
        """Test basic set/get operation."""
        await file_cache.set("test_key", "test_value")
        result = await file_cache.get("test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, file_cache):
        """Test get on non-existent key returns None."""
        result = await file_cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, file_cache):
        """Test delete operation."""
        await file_cache.set("delete_key", "value")
        await file_cache.delete("delete_key")
        result = await file_cache.get("delete_key")
        assert result is None


class TestFileCacheHash:
    """Test hash operations."""

    @pytest.mark.asyncio
    async def test_hset_and_hget(self, file_cache):
        """Test hash set/get."""
        await file_cache.hset("hash_name", "field1", "value1")
        result = await file_cache.hget("hash_name", "field1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_hset_mapping(self, file_cache):
        """Test hash set with mapping."""
        await file_cache.hset("hash_name", mapping={"a": "1", "b": "2"})
        result = await file_cache.hgetall("hash_name")
        assert result == {"a": "1", "b": "2"}

    @pytest.mark.asyncio
    async def test_hgetall_nonexistent(self, file_cache):
        """Test hgetall on non-existent hash returns empty dict."""
        result = await file_cache.hgetall("nonexistent")
        assert result == {}


class TestFileCacheSet:
    """Test set operations."""

    @pytest.mark.asyncio
    async def test_sadd_and_smembers(self, file_cache):
        """Test set add and members."""
        await file_cache.sadd("set_name", "member1", "member2")
        result = await file_cache.smembers("set_name")
        assert result == {"member1", "member2"}

    @pytest.mark.asyncio
    async def test_srem(self, file_cache):
        """Test set remove."""
        await file_cache.sadd("set_name", "a", "b", "c")
        await file_cache.srem("set_name", "b")
        result = await file_cache.smembers("set_name")
        assert result == {"a", "c"}

    @pytest.mark.asyncio
    async def test_sismember(self, file_cache):
        """Test set membership check."""
        await file_cache.sadd("set_name", "member")
        assert await file_cache.sismember("set_name", "member") is True
        assert await file_cache.sismember("set_name", "nonmember") is False


class TestFileCacheList:
    """Test list operations."""

    @pytest.mark.asyncio
    async def test_lpush_and_lrange(self, file_cache):
        """Test list push and range."""
        await file_cache.lpush("list_name", "item1", "item2")
        result = await file_cache.lrange("list_name", 0, -1)
        # Implementation appends items in order, so item1, item2
        assert result == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_ltrim(self, file_cache):
        """Test list trim."""
        await file_cache.lpush("list_name", "a", "b", "c", "d")
        await file_cache.ltrim("list_name", 0, 1)
        result = await file_cache.lrange("list_name", 0, -1)
        # lpush adds in order: a, b, c, d; ltrim(0, 1) keeps first 2
        assert result == ["a", "b"]


class TestFileCacheIncr:
    """Test increment operations."""

    @pytest.mark.asyncio
    async def test_incr_new_key(self, file_cache):
        """Test increment on new key starts at 1."""
        result = await file_cache.incr("counter")
        assert result == 1

    @pytest.mark.asyncio
    async def test_incr_existing(self, file_cache):
        """Test increment on existing key."""
        await file_cache.set("counter", "5")
        result = await file_cache.incr("counter")
        assert result == 6


class TestFileCacheExpire:
    """Test expiration operations."""

    @pytest.mark.asyncio
    async def test_setex(self, file_cache):
        """Test set with expiration."""
        await file_cache.setex("expire_key", 3600, "value")
        result = await file_cache.get("expire_key")
        assert result == "value"
        # Check key exists (TTL checking is implementation dependent)
        exists = await file_cache.exists("expire_key")
        assert exists == 1  # Returns int, not bool


class TestFileCacheExists:
    """Test exists operation."""

    @pytest.mark.asyncio
    async def test_exists_true(self, file_cache):
        """Test exists returns 1 for existing key."""
        await file_cache.set("exists_key", "value")
        result = await file_cache.exists("exists_key")
        assert result == 1  # Redis-compatible: returns int

    @pytest.mark.asyncio
    async def test_exists_false(self, file_cache):
        """Test exists returns 0 for non-existing key."""
        result = await file_cache.exists("nonexistent")
        assert result == 0  # Redis-compatible: returns int


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
