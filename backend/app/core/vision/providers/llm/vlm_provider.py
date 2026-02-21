import logging
import time
from typing import Optional

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import VisionResult, VisionTask
from app.infrastructure.llm.vision import VisionLLMFactory, get_vision_llm

logger = logging.getLogger(__name__)


class MultimodalVLMProvider(VisionProvider):
    """
    Multimodal VLM provider (GPT-4o, Claude 3, etc.)
    """

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

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VisionResult:
        """Process vision task using VLM."""
        start_time = time.time()
        
        # Default prompt if none provided
        if not prompt:
            if task == VisionTask.CAPTION:
                prompt = "Describe this image in detail."
            elif task == VisionTask.ANALYZE:
                prompt = "Analyze this UI screenshot and provide a structured breakdown."
            else:
                prompt = "Describe this image."

        try:
            # Logic moved to VisionLLMFactory
            model = kwargs.get("model") or "gpt-4o"
            llm = get_vision_llm(model_name=model)
            
            # Create Message
            message = VisionLLMFactory.create_image_message(image_source, prompt)
            
            # Invoke
            response = await llm.ainvoke([message])
            
            latency = (time.time() - start_time) * 1000
            
            return VisionResult(
                task=task,
                success=True,
                summary=response.content,
                raw_output=response,
                screenshot_path=image_source,
                latency_ms=latency,
                metadata={"model": model}
            )

        except Exception as e:
            logger.error(f"MultimodalVLMProvider process failed: {e}")
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": str(e)}
            )
