import logging
import time

from app.infrastructure.vision.router import get_vision_router
from app.infrastructure.vision.types import VisionResult, VisionTask
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class VisionEngine:
    """
    Core facade for the Vision Subsystem.
    Provides a unified entry point for all vision-related operations.
    """

    def __init__(self):
        # Use singleton instance to avoid repeated initialization
        self.router = get_vision_router()

    async def process(self, task: VisionTask, image_source: str, prompt: str | None = None, **kwargs) -> VisionResult:
        """
        Main entry point to process any vision task.
        """
        start_time = time.time()

        # Specialized Logic: DETECTION (Multiple Providers)
        if task == VisionTask.DETECT:
            from app.infrastructure.vision.pipeline.manager import pipeline_manager

            elements, screenshot_path = await pipeline_manager.perceive(
                screenshot_path=image_source, device_id=kwargs.get("device_id")
            )
            result = VisionResult(
                task=task,
                success=True,
                elements=elements,
                screenshot_path=screenshot_path or image_source,
                summary=f"Detected {len(elements)} items using PipelineManager.",
            )

        else:
            # Standard Routing for single-provider tasks
            provider = await self.router.get_provider(task, **kwargs)
            if not provider:
                logger.error(f"VisionEngine: No provider found for task {task}")
                return VisionResult(task=task, success=False, metadata={"error": "No available provider"})

            logger.info(f"VisionEngine: Routing task {task} to {provider.name}")

            # 3. Execution (Standard)
            try:
                result = await provider.process(task, image_source, prompt, **kwargs)
            except Exception as e:
                logger.exception(f"VisionEngine: Execution failed in {provider.name}")
                result = VisionResult(task=task, success=False, metadata={"error": str(e)})

        # 4. Finalize
        result.latency_ms = elapsed_ms(start_time)

        return result


# Singleton instance
vision_engine = VisionEngine()
