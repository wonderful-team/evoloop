"""
Fusion Pipeline - Parallel perception with result merging.

Runs multiple perception providers in parallel and merges results
for comprehensive UI element detection.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Any

from app.domain.tools.environment.perception.base import (
    PerceptionProvider,
    PerceptionResult,
    UIElement,
)
from app.domain.tools.environment.perception.cache import scene_cache
from app.domain.tools.environment.perception.providers.android_a11y import android_a11y_provider
from app.domain.tools.environment.perception.providers.ocr import ocr_provider
from app.domain.tools.environment.perception.providers.macos_ax import macos_ax_provider

logger = logging.getLogger(__name__)


def smart_compress(image_path: str, max_width: int = 1280) -> str:
    """
    Compress screenshot while preserving UI element clarity.
    
    Args:
        image_path: Path to original image
        max_width: Maximum width (default 1280px)
        
    Returns:
        Path to compressed image
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed, skipping compression. Install with: pip install Pillow")
        return image_path
    
    try:
        img = Image.open(image_path)
        
        # Only resize if larger than max_width
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Save as WebP for better compression
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"compressed_{timestamp}.webp"
        )
        img.save(output_path, 'WEBP', quality=90)
        
        original_size = os.path.getsize(image_path)
        compressed_size = os.path.getsize(output_path)
        logger.info(f"[Compress] {original_size//1024}KB → {compressed_size//1024}KB ({100*compressed_size//original_size}%)")
        
        return output_path
    except Exception as e:
        logger.warning(f"Compression failed: {e}, using original")
        return image_path



def merge_elements(results: list[PerceptionResult]) -> list[UIElement]:
    """
    Merge elements from multiple perception sources.
    
    Deduplicates overlapping elements, preferring higher confidence
    and more complete information.
    
    Args:
        results: List of perception results
        
    Returns:
        Merged list of unique elements
    """
    all_elements: list[UIElement] = []
    
    for result in results:
        all_elements.extend(result.elements)
    
    if not all_elements:
        return []
    
    # Sort by confidence (descending) so higher confidence elements are processed first
    all_elements.sort(key=lambda e: e.confidence, reverse=True)
    
    merged: list[UIElement] = []
    
    def is_overlapping(e1: UIElement, e2: UIElement, threshold: float = 0.5) -> bool:
        """Check if two elements significantly overlap."""
        # Calculate intersection
        x1 = max(e1.x - e1.width//2, e2.x - e2.width//2)
        y1 = max(e1.y - e1.height//2, e2.y - e2.height//2)
        x2 = min(e1.x + e1.width//2, e2.x + e2.width//2)
        y2 = min(e1.y + e1.height//2, e2.y + e2.height//2)
        
        if x1 >= x2 or y1 >= y2:
            return False
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = max(e1.width * e1.height, 1)
        area2 = max(e2.width * e2.height, 1)
        min_area = min(area1, area2)
        
        return intersection / min_area > threshold
    
    for element in all_elements:
        # Check if this element overlaps with any already merged element
        overlapping = None
        for i, existing in enumerate(merged):
            if is_overlapping(element, existing):
                overlapping = i
                break
        
        if overlapping is not None:
            # Merge: keep the one with more text or higher confidence
            existing = merged[overlapping]
            if (len(element.text) > len(existing.text) or 
                (len(element.text) == len(existing.text) and element.confidence > existing.confidence)):
                merged[overlapping] = element
        else:
            merged.append(element)
    
    # Re-assign IDs sequentially
    for i, element in enumerate(merged):
        element.id = i
    
    return merged


class FusionPipeline:
    """
    Orchestrates multiple perception providers for comprehensive UI detection.
    
    Features:
    - Parallel execution of providers
    - Intelligent scene caching
    - Result merging and deduplication
    - Smart screenshot compression
    """
    
    def __init__(self):
        self.providers: list[PerceptionProvider] = [
            android_a11y_provider,
            macos_ax_provider,
            ocr_provider,
        ]
    
    async def perceive(
        self,
        screenshot_path: str | None = None,
        device_id: str | None = None,
        use_cache: bool = True,
    ) -> tuple[list[UIElement], str | None]:
        """
        Run perception pipeline to extract UI elements.
        
        Args:
            screenshot_path: Optional path to screenshot
            device_id: Optional device identifier
            use_cache: Whether to use scene caching
            
        Returns:
            Tuple of (elements, compressed_screenshot_path)
        """
        compressed_path = None
        
        # Compress screenshot if provided
        if screenshot_path and os.path.exists(screenshot_path):
            compressed_path = smart_compress(screenshot_path)
            
            # Check cache
            if use_cache:
                scene_hash = scene_cache.compute_hash(compressed_path)
                cached = scene_cache.get(scene_hash)
                if cached is not None:
                    return cached, compressed_path
        
        # Run available providers in parallel
        available_providers = []
        for provider in self.providers:
            if await provider.is_available():
                available_providers.append(provider)
        
        if not available_providers:
            logger.warning("[FusionPipeline] No providers available")
            return [], compressed_path
        
        # Execute in parallel
        tasks = [
            provider.extract(
                screenshot_path=compressed_path or screenshot_path,
                device_id=device_id,
            )
            for provider in available_providers
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Provider {available_providers[i].name} failed: {result}")
            else:
                valid_results.append(result)
        
        # Merge results
        elements = merge_elements(valid_results)
        
        # Cache results
        if use_cache and compressed_path:
            scene_hash = scene_cache.compute_hash(compressed_path)
            scene_cache.put(scene_hash, elements, compressed_path)
        
        logger.info(f"[FusionPipeline] Total: {len(elements)} elements from {len(valid_results)} providers")
        
        return elements, compressed_path
    
    def format_for_prompt(self, elements: list[UIElement], max_elements: int = 30) -> str:
        """
        Format elements for inclusion in LLM prompt.
        
        Args:
            elements: List of UI elements
            max_elements: Maximum elements to include
            
        Returns:
            Formatted string for prompt
        """
        if not elements:
            return "No UI elements detected."
        
        # Sort by Y coordinate (top to bottom), then X (left to right)
        sorted_elements = sorted(elements, key=lambda e: (e.y, e.x))
        
        # Limit to max_elements
        if len(sorted_elements) > max_elements:
            sorted_elements = sorted_elements[:max_elements]
        
        lines = ["屏幕元素列表 (Screen Elements):"]
        for element in sorted_elements:
            lines.append(element.to_prompt_line())
        
        if len(elements) > max_elements:
            lines.append(f"... and {len(elements) - max_elements} more elements")
        
        return "\n".join(lines)


# Singleton
fusion_pipeline = FusionPipeline()
