import asyncio
import logging

from app.core.config import settings
from app.infrastructure.vision.providers.base import VisionProvider
from app.infrastructure.vision.providers.llm.vlm_provider import MultimodalVLMProvider
from app.infrastructure.vision.providers.ocr.android_vision import AndroidVisionOCRProvider
from app.infrastructure.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.infrastructure.vision.types import VisionTask

logger = logging.getLogger(__name__)


class VisionRouter:
    """
    Intelligent router for vision tasks.
    Determines the best provider based on task type, cost, and availability.

    Performance Note: OCR providers disabled by default (slow: ~1500ms).
    Set ENABLE_VISION_OCR=True to enable OCR tasks.

    Note: This class implements Singleton pattern with lazy initialization
    for optimal performance. Use get_vision_router() to get the global instance.
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Avoid re-initialization
        if self._initialized:
            return

        self.providers: list[VisionProvider] = [
            MultimodalVLMProvider(),
        ]

        # OCR providers lazy initialization
        # They will be loaded on first OCR request if enabled
        self._ocr_enabled = settings.ENABLE_VISION_OCR
        self._ocr_providers_loaded = False
        self._android_ocr_provider = None
        self._macos_ocr_provider = None

        self._initialized = True

    def _ensure_ocr_loaded(self):
        """Lazy load OCR providers on first use"""
        if not self._ocr_providers_loaded and self._ocr_enabled:
            self._android_ocr_provider = AndroidVisionOCRProvider()
            self._macos_ocr_provider = MacOSVisionOCRProvider()
            self.providers.append(self._android_ocr_provider)
            self.providers.append(self._macos_ocr_provider)
            self._ocr_providers_loaded = True
            logger.warning("[VisionRouter] OCR enabled (slow performance)")

    async def get_provider(self, task: VisionTask, **kwargs) -> VisionProvider | None:
        """
        Route task to the best available provider.
        """
        # Lazy load OCR if needed
        if task == VisionTask.OCR and self._ocr_enabled:
            self._ensure_ocr_loaded()

        # Logic:
        # 1. Capture/OCR -> Local if available
        # 2. Analysis/Caption -> LLM
        # 3. Explicit override in kwargs

        explicit_provider = kwargs.get("provider_name")
        if explicit_provider:
            for p in self.providers:
                if p.name == explicit_provider and await p.is_available():
                    return p

        # Default Routing
        if self._ocr_enabled and task == VisionTask.OCR:
            from app.core.context import ContextManager

            ctx = ContextManager.current()
            current_ecosystem = ctx.metadata.get("current_ecosystem")

            # 1. Android Specific OCR
            if kwargs.get("on_android") or current_ecosystem == "android":
                for p in self.providers:
                    if isinstance(p, AndroidVisionOCRProvider) and await p.is_available():
                        return p

            # 2. MacOS Native Vision (Retina Aware)
            else:
                for p in self.providers:
                    if (
                        isinstance(p, MacOSVisionOCRProvider)
                        and not isinstance(p, AndroidVisionOCRProvider)
                        and await p.is_available()
                    ):
                        return p

        if task in [VisionTask.ANALYZE, VisionTask.CAPTION, VisionTask.COMPARE]:
            # Prefer Multimodal VLM
            for p in self.providers:
                if isinstance(p, MultimodalVLMProvider) and await p.is_available():
                    return p

        # Fallback: First available
        for p in self.providers:
            if await p.is_available():
                return p

        return None


# Global singleton instance
_vision_router_instance = None


def get_vision_router() -> VisionRouter:
    """
    Get the global VisionRouter singleton instance.

    This function returns a shared instance to avoid repeated initialization
    and OCR provider loading. Use this instead of creating new VisionRouter().

    Returns:
        VisionRouter: The global singleton instance
    """
    global _vision_router_instance
    if _vision_router_instance is None:
        _vision_router_instance = VisionRouter()
    return _vision_router_instance
