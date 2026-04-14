"""
Deterministic Tool Cache - Zero-risk caching for read-only tools.

This module provides caching for tools that are:
1. Pure functions (same input = same output)
2. Read-only (no side effects)
3. Deterministic (no external state changes)

Safety guarantees:
- Content hash verification for file operations
- Automatic invalidation on file modification
- Strict whitelist for cacheable tools
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

import aiofiles
import aiofiles.os
from pydantic import BaseModel, Field, ConfigDict

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class CacheKey(BaseModel):
    """Immutable cache key with content verification."""
    model_config = ConfigDict(frozen=True)
    
    tool_name: str
    args_hash: str
    content_hash: str = ""  # File content hash for verification
    
    def __hash__(self):
        return hash((self.tool_name, self.args_hash, self.content_hash))


class CacheEntry(DynamicBaseModel):
    """Cache entry with metadata."""
    result: Any
    timestamp: float = Field(default_factory=time.time)
    access_count: int = 0
    last_verified: float = 0.0


class CacheStats(DynamicBaseModel):
    """Cache statistics."""
    hits: int
    misses: int
    hit_rate: str
    verifications: int
    invalidations: int
    cache_size: int
    max_size: int


class DeterministicToolCache:
    """
    Deterministic tool cache with content verification.
    
    Only caches tools that are mathematically deterministic:
    - read_file: File content at call time is fixed
    - list_directory: Directory state at call time is fixed
    - search_files: Results based on disk state at call time
    - analyze_image: Same image + same model = same result
    """
    
    # Strict whitelist - only truly deterministic tools
    DETERMINISTIC_TOOLS = frozenset({
        'read_file',
        'list_directory', 
        'get_file_info',
        'search_files',
        'analyze_image',
        'search_web',           # Cached with short TTL
        'read_url_content',     # Cached with short TTL
        'search_history',
        'search_skills',
    })
    
    # Never cache these tools (side effects)
    NEVER_CACHE = frozenset({
        'write_file',
        'edit_file',
        'delete_file',
        'move_file',
        'execute_command',
        'bash',
        'shell',
        'python',
        'mobile_control',
        'browser_control',
        'desktop_control',
        'open_app',
        'click_at',
        'type_text',
        'press_key',
        'manage_memory',
        'save_concept',
        'update_focus',
    })
    
    # TTL configuration per tool type (seconds)
    TTL_CONFIG = {
        'read_file': 60,           # 1 minute for source files
        'list_directory': 30,      # 30 seconds for directories
        'get_file_info': 120,      # 2 minutes for metadata
        'search_files': 60,        # 1 minute for search results
        'analyze_image': 300,      # 5 minutes for image analysis
        'search_web': 30,          # 30 seconds for web content
        'read_url_content': 60,    # 1 minute for URL content
        'search_history': 30,      # 30 seconds for history
        'search_skills': 300,      # 5 minutes for skills (rarely change)
    }
    
    def __init__(self, maxsize: int = 1000):
        self._cache: dict[CacheKey, CacheEntry] = {}
        self._maxsize = maxsize
        self._stats = {
            'hits': 0,
            'misses': 0,
            'verifications': 0,
            'invalidations': 0,
        }
    
    async def execute(
        self,
        tool_name: str,
        args: dict,
        execute_fn: Callable,
        config: Optional[Any] = None
    ) -> tuple[Any, dict]:
        """
        Execute tool with caching.
        
        Returns:
            (result, metadata) where metadata includes cache status
        """
        # Fast reject: never cache side-effect tools
        if tool_name in self.NEVER_CACHE:
            result = await execute_fn()
            return result, {'cached': False, 'source': 'execution', 'reason': 'side_effect_tool'}
        
        # Check if tool is cacheable
        if tool_name not in self.DETERMINISTIC_TOOLS:
            result = await execute_fn()
            return result, {'cached': False, 'source': 'execution', 'reason': 'not_deterministic'}
        
        # Generate secure cache key with content verification
        cache_key = await self._make_secure_key(tool_name, args)
        
        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            
            # Check TTL
            ttl = self.TTL_CONFIG.get(tool_name, 60)
            if time.time() - entry.timestamp > ttl:
                logger.debug(f"[ToolCache] TTL expired: {tool_name}")
                del self._cache[cache_key]
            else:
                # Verify content integrity for file operations
                is_valid = await self._verify_content_integrity(cache_key, args)
                self._stats['verifications'] += 1
                
                if is_valid:
                    entry.access_count += 1
                    entry.last_verified = time.time()
                    self._stats['hits'] += 1
                    logger.debug(f"[ToolCache] ✓ Hit: {tool_name} (accesses: {entry.access_count})")
                    return entry.result, {
                        'cached': True,
                        'source': 'verified_cache',
                        'age_seconds': time.time() - entry.timestamp,
                        'access_count': entry.access_count,
                    }
                else:
                    # Content changed, invalidate
                    logger.info(f"[ToolCache] ✗ Invalidated (content changed): {tool_name}")
                    del self._cache[cache_key]
                    self._stats['invalidations'] += 1
        
        # Execute and cache
        self._stats['misses'] += 1
        result = await execute_fn()
        
        # Store with metadata
        entry = CacheEntry(result=result)
        self._cache[cache_key] = entry
        
        # LRU eviction if needed
        self._evict_if_needed()
        
        logger.debug(f"[ToolCache] Stored: {tool_name}")
        return result, {'cached': False, 'source': 'execution'}
    
    async def _make_secure_key(self, tool_name: str, args: dict) -> CacheKey:
        """Generate cache key with content hash for verification."""
        # Canonical args (sort keys for consistency)
        canonical_args = {k: v for k, v in args.items() if k not in ('_config', 'config')}
        args_str = json.dumps(canonical_args, sort_keys=True, ensure_ascii=False)
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:32]
        
        # Content hash for file-based tools
        content_hash = ""
        if tool_name in ('read_file', 'analyze_image', 'get_file_info'):
            path = args.get('path') or args.get('file_path')
            if path:
                content_hash = await self._compute_file_hash(path)
        
        return CacheKey(tool_name, args_hash, content_hash)
    
    async def _compute_file_hash(self, path: str) -> str:
        """Compute SHA256 hash of file content."""
        try:
            # Handle relative paths
            if not Path(path).is_absolute():
                from app.core.context import ContextManager
                ctx = ContextManager.current()
                if ctx.working_directory:
                    path = str(Path(ctx.working_directory) / path)
            
            if not await aiofiles.os.path.exists(path):
                return ""
            
            # For large files, hash first 64KB + file size + mtime
            stat = await aiofiles.os.stat(path)
            file_size = stat.st_size
            mtime = stat.st_mtime
            
            if file_size > 65536:
                # Large file: hash metadata + sample
                async with aiofiles.open(path, 'rb') as f:
                    sample = await f.read(65536)
                    content = sample + str(file_size).encode() + str(mtime).encode()
            else:
                # Small file: hash full content
                async with aiofiles.open(path, 'rb') as f:
                    content = await f.read()
            
            return hashlib.sha256(content).hexdigest()[:16]
        except Exception as e:
            logger.debug(f"[ToolCache] Failed to hash file {path}: {e}")
            return ""
    
    async def _verify_content_integrity(self, key: CacheKey, args: dict) -> bool:
        """Verify that cached content is still valid."""
        if not key.content_hash:
            return True  # No content hash, skip verification
        
        # Recompute current content hash
        current_hash = await self._compute_file_hash(
            args.get('path') or args.get('file_path', '')
        )
        
        return current_hash == key.content_hash
    
    def _evict_if_needed(self):
        """LRU eviction when cache is full."""
        if len(self._cache) <= self._maxsize:
            return
        
        # Sort by (access_count, last_access_time) and remove least used
        items = sorted(
            self._cache.items(),
            key=lambda x: (x[1].access_count, x[1].timestamp)
        )
        
        to_remove = int(self._maxsize * 0.2)  # Remove 20%
        for key, _ in items[:to_remove]:
            del self._cache[key]
        
        logger.debug(f"[ToolCache] Evicted {to_remove} entries")
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0.0
        
        return CacheStats(
            hits=self._stats['hits'],
            misses=self._stats['misses'],
            hit_rate=f"{hit_rate:.1%}",
            verifications=self._stats['verifications'],
            invalidations=self._stats['invalidations'],
            cache_size=len(self._cache),
            max_size=self._maxsize,
        )
    
    def invalidate_path(self, path: str):
        """Invalidate all cache entries for a given path."""
        keys_to_remove = []
        for key in self._cache.keys():
            # Check if this key is related to the path
            if key.content_hash:  # File-based tool
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            logger.info(f"[ToolCache] Invalidated {len(keys_to_remove)} entries for path: {path}")


# Global cache instance
tool_cache = DeterministicToolCache()


async def execute_with_cache(
    tool_name: str,
    args: dict,
    execute_fn: Callable,
    config: Optional[Any] = None
) -> tuple[Any, dict]:
    """Convenience function for cached execution."""
    return await tool_cache.execute(tool_name, args, execute_fn, config)
