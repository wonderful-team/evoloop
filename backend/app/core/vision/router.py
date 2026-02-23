import logging

from app.core.config import settings
from app.core.vision.providers.base import VisionProvider
from app.core.vision.providers.llm.vlm_provider import MultimodalVLMProvider
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

logger = logging.getLogger(__name__)


class VisionRouter:
    """
    Intelligent router for vision tasks.
    Determines the best provider based on task type, cost, and availability.

    Performance Note: OCR providers disabled by default (slow: ~1500ms).
    Set ENABLE_VISION_OCR=True to enable OCR tasks.
    """

    def __init__(self):
        self.providers: list[VisionProvider] = [
            MacOSVisionOCRProvider(),
            LocalOCRProvider(),
            MultimodalVLMProvider(),
        ]

    async def get_provider(self, task: VisionTask, **kwargs) -> VisionProvider | None:
        """
        Route task to the best available provider.
        """
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
        if task == VisionTask.OCR:
            # Prefer native MacOS Vision OCR if on Mac
            for p in self.providers:
                if isinstance(p, MacOSVisionOCRProvider) and await p.is_available():
                    return p
            # Fallback to general local OCR
            for p in self.providers:
                if isinstance(p, LocalOCRProvider) and await p.is_available():
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
