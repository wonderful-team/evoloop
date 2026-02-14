import logging
from typing import List, Optional

from app.core.vision.providers.base import VisionProvider
from app.core.vision.providers.ocr.ocr_provider import LocalOCRProvider
from app.core.vision.providers.llm.vlm_provider import MultimodalVLMProvider
from app.core.vision.types import VisionTask

logger = logging.getLogger(__name__)


class VisionRouter:
    """
    Intelligent router for vision tasks.
    Determines the best provider based on task type, cost, and availability.
    """

    def __init__(self):
        self.providers: List[VisionProvider] = [
            LocalOCRProvider(),
            MultimodalVLMProvider(),
        ]

    async def get_provider(self, task: VisionTask, **kwargs) -> Optional[VisionProvider]:
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
            # Prefer local OCR
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
