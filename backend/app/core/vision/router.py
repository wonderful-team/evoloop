import logging

from app.core.config import settings
from app.core.vision.providers.base import VisionProvider
from app.core.vision.providers.llm.vlm_provider import MultimodalVLMProvider
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.providers.ocr.android_vision import AndroidVisionOCRProvider
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
            MultimodalVLMProvider(),
        ]

        # OCR providers disabled by default for performance
        # Enable with ENABLE_VISION_OCR=1 environment variable
        if settings.ENABLE_VISION_OCR:
            self.providers.append(AndroidVisionOCRProvider())
            self.providers.append(MacOSVisionOCRProvider())
            logger.warning("[VisionRouter] OCR enabled (slow performance)")

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
        if settings.ENABLE_VISION_OCR and task == VisionTask.OCR:
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
                    if isinstance(p, MacOSVisionOCRProvider) and not isinstance(p, AndroidVisionOCRProvider) and await p.is_available():
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
