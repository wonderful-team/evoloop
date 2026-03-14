import logging
import time

from langchain_core.messages import SystemMessage
from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import VisionResult, VisionTask
from app.infrastructure.llm.vision import VisionLLMFactory, get_vision_llm

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = (
    "You are a precise vision analysis assistant. "
    "Analyze the provided image(s) accurately. "
    "Be concise, direct, and avoid any repetitive loops in your response. "
    "If you are describing a UI, focus on the functional elements and their current state."
)


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
        prompt: str | None = None,
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

        llm = get_vision_llm()

        # Create Messages (System + Human)
        system_msg = SystemMessage(content=VISION_SYSTEM_PROMPT)
        human_msg = VisionLLMFactory.create_image_message(image_source, prompt)

        # Invoke
        response = await llm.ainvoke([system_msg, human_msg])

        result = VisionResult(
            task=task,
            success=True,
            summary=response.content,
            raw_output=response,
            screenshot_path=image_source,
            latency_ms=(time.time() - start_time) * 1000,
        )

        return result
