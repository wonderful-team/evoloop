import logging
import time

from app.core.engine.message.native_classes import SystemMessage
from app.infrastructure.vision.llm import VisionLLMFactory, get_vision_llm_async
from app.infrastructure.vision.providers.base import VisionProvider
from app.infrastructure.vision.types import VisionResult, VisionTask
from app.utils.template import render_template
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


def _get_vision_system_prompt() -> str:
    try:
        return render_template("core/vision/vision_analysis.prompt.j2")
    except Exception as e:
        logger.warning(f"Failed to load vision prompt template: {e}", exc_info=True)
        return "Analyze the provided image(s) accurately."


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

        # 无可用视觉模型时给 Agent 明确的引导性错误（而非裸 ValueError），
        # 便于其降级（如像素统计/OCR 代码方案）或提示用户配置
        try:
            await get_vision_llm_async()
        except ValueError as e:
            return VisionResult(
                task=task,
                success=False,
                summary=(
                    f"Error: 视觉理解不可用：{e}。"
                    "请配置 VISION_MODEL 为平台目录中 supports_vision 的模型，"
                    "或由 Agent 使用 bash 像素统计等代码方案降级处理。"
                ),
            )

        # Default prompt if none provided
        if not prompt:
            if task == VisionTask.CAPTION:
                prompt = "Describe this image in detail."
            elif task == VisionTask.ANALYZE:
                prompt = "Analyze this UI screenshot and provide a structured breakdown."
            else:
                prompt = "Describe this image."

        llm = await get_vision_llm_async()

        # Create Messages (System + Human with image)
        system_msg = SystemMessage(content=_get_vision_system_prompt())
        human_msg = VisionLLMFactory.create_image_message(image_source, prompt)

        # Invoke LLM directly (Vision needs special image handling, not suitable for InternalLLMService)
        response = await llm.ainvoke([system_msg, human_msg])

        result = VisionResult(
            task=task,
            success=True,
            summary=response.content,
            raw_output=response,
            screenshot_path=image_source,
            latency_ms=elapsed_ms(start_time),
        )

        return result
