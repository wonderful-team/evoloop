import hashlib
import logging
import time
from typing import Dict, Tuple

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import VisionResult, VisionTask
from app.infrastructure.llm.vision import VisionLLMFactory, get_vision_llm

logger = logging.getLogger(__name__)


class MultimodalVLMProvider(VisionProvider):
    """
    Multimodal VLM provider (GPT-4o, Claude 3, etc.)
    """

    # Simple cache for vision analysis results (image_hash + prompt -> result)
    _analysis_cache: Dict[Tuple[str, str], Tuple[VisionResult, float]] = {}
    _cache_ttl: float = 60.0  # Cache results for 60 seconds

    @property
    def name(self) -> str:
        return "multimodal_vlm"

    @property
    def cost_factor(self) -> float:
        return 1.0  # High cost - API calls

    async def is_available(self) -> bool:
        # Assuming if config exists, it's available.
        # Real check might involve API key validation.
        return True

    def _get_image_hash(self, image_path: str) -> str:
        """Generate a quick hash of the image file for caching."""
        try:
            with open(image_path, 'rb') as f:
                # Read first 8KB + last 8KB for quick hash
                head = f.read(8192)
                f.seek(-8192, 2)
                tail = f.read(8192)
                return hashlib.md5(head + tail).hexdigest()[:16]
        except Exception:
            return ""

    def _check_cache(self, image_hash: str, prompt: str) -> VisionResult | None:
        """Check if we have a cached result for this image + prompt."""
        cache_key = (image_hash, prompt)
        if cache_key in self._analysis_cache:
            result, timestamp = self._analysis_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.info(f"[VLM] Cache hit for image hash {image_hash[:8]}")
                return result
            else:
                # Expired
                del self._analysis_cache[cache_key]
        return None

    def _store_cache(self, image_hash: str, prompt: str, result: VisionResult) -> None:
        """Store result in cache."""
        cache_key = (image_hash, prompt)
        self._analysis_cache[cache_key] = (result, time.time())
        # Limit cache size
        if len(self._analysis_cache) > 50:
            oldest_key = min(self._analysis_cache.keys(), key=lambda k: self._analysis_cache[k][1])
            del self._analysis_cache[oldest_key]

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: str | None = None,
        **kwargs
    ) -> VisionResult:
        """Process vision task using VLM with caching."""
        start_time = time.time()

        # Default prompt if none provided
        if not prompt:
            if task == VisionTask.CAPTION:
                prompt = "Describe this image in detail."
            elif task == VisionTask.ANALYZE:
                prompt = "Analyze this UI screenshot and provide a structured breakdown."
            else:
                prompt = "Describe this image."

        # Check cache for ANALYZE tasks (avoid repeated API calls)
        image_hash = ""
        if task == VisionTask.ANALYZE and image_source:
            image_hash = self._get_image_hash(image_source)
            if image_hash:
                cached = self._check_cache(image_hash, prompt)
                if cached:
                    # Return cached result with updated metadata
                    cached.latency_ms = 0  # Indicate cache hit
                    cached.metadata["cached"] = True
                    return cached

        # Default prompt if none provided
        if not prompt:
            if task == VisionTask.CAPTION:
                prompt = "Describe this image in detail."
            elif task == VisionTask.ANALYZE:
                prompt = "Analyze this UI screenshot and provide a structured breakdown."
            else:
                prompt = "Describe this image."

        llm = get_vision_llm()

        # Create Message
        message = VisionLLMFactory.create_image_message(image_source, prompt)

        # Invoke
        response = await llm.ainvoke([message])

        result = VisionResult(
            task=task,
            success=True,
            summary=response.content,
            raw_output=response,
            screenshot_path=image_source,
            latency_ms=(time.time() - start_time) * 1000,
        )

        # Store in cache for ANALYZE tasks
        if task == VisionTask.ANALYZE and image_source and image_hash:
            self._store_cache(image_hash, prompt, result)

        return result
