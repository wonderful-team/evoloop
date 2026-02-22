"""
Scene Cache - Intelligent caching for perception results.

Uses perceptual hashing to detect similar scenes and avoid
redundant perception calls.
"""

import logging
import time
from dataclasses import dataclass

from app.core.vision.types import UIElement

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached perception result."""
    scene_hash: str
    elements: list[UIElement]
    timestamp: float
    screenshot_path: str | None = None


class SceneCache:
    """
    Cache for perception results based on scene similarity.
    
    Uses perceptual hashing to detect when the screen hasn't changed
    significantly, allowing reuse of previous perception results.
    """

    def __init__(
        self,
        max_entries: int = 10,
        ttl_seconds: float = 30.0,
        similarity_threshold: int = 8,
    ):
        """
        Initialize the scene cache.
        
        Args:
            max_entries: Maximum number of cached entries
            ttl_seconds: Time-to-live for cache entries
            similarity_threshold: Max hamming distance for "same scene"
        """
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self._cache: list[CacheEntry] = []
        self._phash_available = self._check_phash()

    def _check_phash(self) -> bool:
        """Check if imagehash library is available."""
        try:
            import imagehash
            from PIL import Image
            return True
        except ImportError:
            logger.warning("imagehash not available, scene caching disabled. Install with: pip install imagehash")
            return False

    def compute_hash(self, screenshot_path: str) -> str | None:
        """
        Compute perceptual hash for a screenshot.
        
        Args:
            screenshot_path: Path to screenshot image
            
        Returns:
            Hash string or None if hashing failed
        """
        if not self._phash_available:
            return None

        try:
            import imagehash
            from PIL import Image

            img = Image.open(screenshot_path)
            # Resize for faster hashing
            img = img.resize((256, 256))
            phash = imagehash.phash(img)
            return str(phash)
        except Exception as e:
            logger.warning(f"Failed to compute scene hash: {e}")
            return None

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """Compute hamming distance between two hex hashes."""
        try:
            import imagehash
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return h1 - h2
        except Exception:
            # Fallback: simple hex comparison
            if len(hash1) != len(hash2):
                return 64  # Max distance

            distance = 0
            for c1, c2 in zip(hash1, hash2):
                b1 = int(c1, 16)
                b2 = int(c2, 16)
                distance += bin(b1 ^ b2).count('1')
            return distance

    def is_same_scene(self, hash1: str | None, hash2: str | None) -> bool:
        """
        Check if two hashes represent the same scene.
        
        Args:
            hash1: First scene hash
            hash2: Second scene hash
            
        Returns:
            True if scenes are similar enough
        """
        if hash1 is None or hash2 is None:
            return False

        distance = self._hamming_distance(hash1, hash2)
        return distance < self.similarity_threshold

    def get(self, scene_hash: str | None) -> list[UIElement] | None:
        """
        Get cached elements for a scene hash.
        
        Args:
            scene_hash: Scene hash to look up
            
        Returns:
            Cached elements or None if not found/expired
        """
        if scene_hash is None:
            return None

        current_time = time.time()

        for entry in self._cache:
            # Check TTL
            if current_time - entry.timestamp > self.ttl_seconds:
                continue

            # Check similarity
            if self.is_same_scene(scene_hash, entry.scene_hash):
                logger.info(f"[SceneCache] Hit! Reusing {len(entry.elements)} elements")
                return entry.elements

        return None

    def put(
        self,
        scene_hash: str | None,
        elements: list[UIElement],
        screenshot_path: str | None = None,
    ) -> None:
        """
        Cache elements for a scene.
        
        Args:
            scene_hash: Scene hash
            elements: Detected elements
            screenshot_path: Path to screenshot
        """
        if scene_hash is None:
            return

        entry = CacheEntry(
            scene_hash=scene_hash,
            elements=elements,
            timestamp=time.time(),
            screenshot_path=screenshot_path,
        )

        # Remove expired entries
        current_time = time.time()
        self._cache = [
            e for e in self._cache
            if current_time - e.timestamp <= self.ttl_seconds
        ]

        # Add new entry
        self._cache.append(entry)

        # Enforce max size
        if len(self._cache) > self.max_entries:
            self._cache = self._cache[-self.max_entries:]

        logger.info(f"[SceneCache] Cached {len(elements)} elements (hash: {scene_hash[:8]}...)")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.info("[SceneCache] Cleared")


# Singleton
scene_cache = SceneCache()
