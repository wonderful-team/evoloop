"""
Tests for DeterministicToolCache

Run with: pytest tests/test_tool_cache.py -v
"""

import asyncio
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the imports before importing our module
import sys
from types import ModuleType

# Create mock modules
for mod_name in ['app', 'app.core', 'app.core.context', 'app.infrastructure']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = ModuleType(mod_name)

# Mock aiofiles
mock_aiofiles = ModuleType('aiofiles')
mock_aiofiles.os = ModuleType('aiofiles.os')
mock_aiofiles.os.path = MagicMock()
mock_aiofiles.os.path.exists = AsyncMock(return_value=True)
mock_aiofiles.os.stat = AsyncMock(return_value=MagicMock(st_size=100, st_mtime=time.time()))
sys.modules['aiofiles'] = mock_aiofiles
sys.modules['aiofiles.os'] = mock_aiofiles.os

# Now import our code
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.tools.cache import (
    CacheKey,
    CacheEntry,
    DeterministicToolCache,
    execute_with_cache,
)


class TestCacheKey:
    """Test CacheKey dataclass."""
    
    def test_cache_key_immutable(self):
        """CacheKey should be hashable and immutable."""
        key1 = CacheKey("read_file", "hash123", "content456")
        key2 = CacheKey("read_file", "hash123", "content456")
        
        assert key1 == key2
        assert hash(key1) == hash(key2)
    
    def test_cache_key_differentiation(self):
        """Different args should produce different keys."""
        key1 = CacheKey("read_file", "hash123", "content456")
        key2 = CacheKey("read_file", "hash123", "content789")
        key3 = CacheKey("list_directory", "hash123", "content456")
        
        assert key1 != key2
        assert key1 != key3


class TestDeterministicToolCache:
    """Test DeterministicToolCache class."""
    
    @pytest.fixture
    def cache(self):
        """Fresh cache instance."""
        return DeterministicToolCache(maxsize=100)
    
    @pytest.fixture
    def mock_tool_result(self):
        """Mock tool execution result."""
        return {"content": "file content", "lines": 10}
    
    @pytest.mark.asyncio
    async def test_never_cache_tools_blocked(self, cache):
        """Tools in NEVER_CACHE should never be cached."""
        execute_fn = AsyncMock(return_value="executed")
        
        for tool_name in ['write_file', 'edit_file', 'execute_command', 'bash']:
            result, meta = await cache.execute(tool_name, {"path": "/tmp/test"}, execute_fn)
            
            assert meta['cached'] is False
            assert meta['reason'] == 'side_effect_tool'
            assert result == "executed"
            execute_fn.assert_called()
            execute_fn.reset_mock()
    
    @pytest.mark.asyncio
    async def test_deterministic_tools_cached(self, cache, mock_tool_result):
        """Deterministic tools should be cached."""
        execute_fn = AsyncMock(return_value=mock_tool_result)
        
        # Mock file hash computation
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="abc123")):
            # First execution - cache miss
            result1, meta1 = await cache.execute(
                'read_file', 
                {'path': '/tmp/test.py'}, 
                execute_fn
            )
            
            assert meta1['cached'] is False
            assert meta1['source'] == 'execution'
            execute_fn.assert_called_once()
            
            # Second execution - cache hit
            execute_fn.reset_mock()
            result2, meta2 = await cache.execute(
                'read_file',
                {'path': '/tmp/test.py'},
                execute_fn
            )
            
            assert meta2['cached'] is True
            assert meta2['source'] == 'verified_cache'
            execute_fn.assert_not_called()  # Should not execute again
            assert result1 == result2
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_on_file_change(self, cache, mock_tool_result):
        """Cache should be invalidated when file content changes."""
        execute_fn = AsyncMock(return_value=mock_tool_result)
        
        # First call with hash "abc123"
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="abc123")):
            await cache.execute('read_file', {'path': '/tmp/test.py'}, execute_fn)
            
            # Second call with different hash (file changed)
            execute_fn.reset_mock()
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="def456")):
            result, meta = await cache.execute('read_file', {'path': '/tmp/test.py'}, execute_fn)
            
            assert meta['cached'] is False  # Should re-execute
            execute_fn.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache, mock_tool_result):
        """Cache entries should expire after TTL."""
        execute_fn = AsyncMock(return_value=mock_tool_result)
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="abc123")):
            # Store with expired timestamp
            await cache.execute('read_file', {'path': '/tmp/test.py'}, execute_fn)
            
            # Manually expire the entry
            for key, entry in list(cache._cache.items()):
                entry.timestamp = time.time() - 3600  # 1 hour ago
            
            execute_fn.reset_mock()
            
            # Should be cache miss due to TTL
            result, meta = await cache.execute('read_file', {'path': '/tmp/test.py'}, execute_fn)
            assert meta['cached'] is False
            execute_fn.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        """Cache should evict old entries when full."""
        cache._maxsize = 5
        execute_fn = AsyncMock(return_value="result")
        
        # Add 5 entries
        for i in range(5):
            with patch.object(cache, '_compute_file_hash', AsyncMock(return_value=f"hash{i}")):
                await cache.execute('read_file', {'path': f'/tmp/file{i}.py'}, execute_fn)
        
        assert len(cache._cache) == 5
        
        # Add 6th entry, should trigger eviction
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="hash5")):
            await cache.execute('read_file', {'path': '/tmp/file5.py'}, execute_fn)
        
        # Should have evicted some entries (20% = 1 entry)
        assert len(cache._cache) <= 5
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache, mock_tool_result):
        """Cache should track statistics correctly."""
        execute_fn = AsyncMock(return_value=mock_tool_result)
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="abc123")):
            # 2 misses
            await cache.execute('read_file', {'path': '/tmp/a.py'}, execute_fn)
            await cache.execute('read_file', {'path': '/tmp/b.py'}, execute_fn)
            
            # 3 hits
            await cache.execute('read_file', {'path': '/tmp/a.py'}, execute_fn)
            await cache.execute('read_file', {'path': '/tmp/a.py'}, execute_fn)
            await cache.execute('read_file', {'path': '/tmp/b.py'}, execute_fn)
        
        stats = cache.get_stats()
        
        assert stats['hits'] == 3
        assert stats['misses'] == 2
        assert stats['hit_rate'] == '60.0%'
    
    def test_tool_categorization(self, cache):
        """Tools should be correctly categorized."""
        # All deterministic tools are safe
        for tool in cache.DETERMINISTIC_TOOLS:
            assert tool not in cache.NEVER_CACHE, f"{tool} should not be in NEVER_CACHE"
        
        # No overlap between categories
        overlap = cache.DETERMINISTIC_TOOLS & cache.NEVER_CACHE
        assert len(overlap) == 0, f"Found overlapping tools: {overlap}"
    
    @pytest.mark.asyncio
    async def test_different_tools_same_args_not_confused(self, cache):
        """Different tools with same args should not share cache."""
        execute_fn = AsyncMock(side_effect=["result1", "result2"])
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="abc123")):
            result1, _ = await cache.execute('read_file', {'path': '/tmp/test'}, execute_fn)
            result2, _ = await cache.execute('list_directory', {'path': '/tmp/test'}, execute_fn)
            
            assert result1 == "result1"
            assert result2 == "result2"
            assert execute_fn.call_count == 2


class TestExecuteWithCache:
    """Test the convenience function."""
    
    @pytest.mark.asyncio
    async def test_execute_with_cache_integration(self):
        """Test the global execute_with_cache function."""
        from app.core.tools.cache import tool_cache
        
        execute_fn = AsyncMock(return_value="test_result")
        
        with patch.object(tool_cache, 'execute', wraps=tool_cache.execute) as mock_execute:
            result, meta = await execute_with_cache(
                'search_files',
                {'pattern': '*.py'},
                execute_fn
            )
            
            assert result == "test_result"
            mock_execute.assert_called_once()


class TestCacheIntegration:
    """Integration tests with realistic scenarios."""
    
    @pytest.mark.asyncio
    async def test_repeated_file_reads_in_same_session(self):
        """Worker reading same file multiple times should use cache."""
        cache = DeterministicToolCache()
        
        file_content = {"content": "def hello(): pass", "path": "/tmp/app.py"}
        execute_fn = AsyncMock(return_value=file_content)
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="stable_hash")):
            # Simulate: read file, analyze, read again to verify
            result1, meta1 = await cache.execute('read_file', {'path': '/tmp/app.py'}, execute_fn)
            
            # Analysis happens here...
            
            result2, meta2 = await cache.execute('read_file', {'path': '/tmp/app.py'}, execute_fn)
            
            # Second read should be cached
            assert meta1['cached'] is False
            assert meta2['cached'] is True
            assert execute_fn.call_count == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_tool_execution_safety(self):
        """Cache should be safe for concurrent access."""
        cache = DeterministicToolCache()
        execute_fn = AsyncMock(return_value="result")
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="hash123")):
            # Simulate 10 concurrent reads of same file
            tasks = [
                cache.execute('read_file', {'path': '/tmp/shared.py'}, execute_fn)
                for _ in range(10)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Should only execute once, rest from cache
            assert execute_fn.call_count == 1
            assert all(r[0] == "result" for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
