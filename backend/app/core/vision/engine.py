import logging
import time

from app.core.environment.event import UiTreeObservedEvent
from app.core.environment.bus import event_bus
from app.core.events.base import system_bus
from app.core.vision.event import (
    VisionProcessCompletedEvent,
    VisionProcessStartedEvent,
)
from app.core.vision.router import get_vision_router
from app.core.vision.types import VisionResult, VisionTask
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


class VisionEngine:
    """
    Core facade for the Vision Subsystem.
    Provides a unified entry point for all vision-related operations.
    """

    def __init__(self):
        # Use singleton instance to avoid repeated initialization
        self.router = get_vision_router()

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: str | None = None,
        **kwargs
    ) -> VisionResult:
        """
        Main entry point to process any vision task.
        """
        start_time = time.time()

        # 1. Publish Start Event
        from app.core.vision.event.publishers import publish_vision_process_started
        await publish_vision_process_started(task.value, image_source)

        # Specialized Logic: DETECTION (Multiple Providers)
        if task == VisionTask.DETECT:
            from app.core.vision.pipeline.manager import pipeline_manager
            elements, screenshot_path = await pipeline_manager.perceive(
                screenshot_path=image_source,
                device_id=kwargs.get("device_id")
            )
            result = VisionResult(
                task=task,
                success=True,
                elements=elements,
                screenshot_path=screenshot_path or image_source,
                summary=f"Detected {len(elements)} items using PipelineManager."
            )

            # --- Passive Atlas Learning ---
            try:
                # 1. Get current context for metadata
                app_info = macos_driver.get_current_app()

                # 2. Publish to Awakening Event Bus for AppAtlasService to consume
                from app.core.environment.event.publishers import publish_ui_tree_observed
                await publish_ui_tree_observed(
                    platform="macos",
                    bundle_id=app_info.get("bundle_id", "unknown"),
                    window_title=app_info.get("title", "unknown"),
                    elements=[e.to_dict() for e in elements],
                    screenshot_hash="",
                )
                logger.debug(f"[VisionEngine] Emitted UiTreeObservedEvent for {app_info.get('bundle_id')}")
            except Exception as e:
                logger.warning(f"[VisionEngine] Failed to emit Atlas event: {e}")
        else:
            # Standard Routing for single-provider tasks
            provider = await self.router.get_provider(task, **kwargs)
            if not provider:
                logger.error(f"VisionEngine: No provider found for task {task}")
                return VisionResult(
                    task=task,
                    success=False,
                    metadata={"error": "No available provider"}
                )

            logger.info(f"VisionEngine: Routing task {task} to {provider.name}")

            # 3. Execution (Standard)
            try:
                result = await provider.process(task, image_source, prompt, **kwargs)
            except Exception as e:
                logger.exception(f"VisionEngine: Execution failed in {provider.name}")
                result = VisionResult(
                    task=task,
                    success=False,
                    metadata={"error": str(e)}
                )

        # 4. Finalize
        result.latency_ms = (time.time() - start_time) * 1000

        # 5. Passive Atlas Learning for non-DETECT tasks
        # Skip Atlas learning for browser contexts (dynamic web pages don't benefit from Atlas)
        enable_atlas = kwargs.get("enable_atlas_learning", True)
        if task != VisionTask.DETECT and result.success and enable_atlas:
            # Check platform
            platform = kwargs.get("platform")
            if not platform:
                platform = "android" if kwargs.get("on_android") else "macos"

            # Dispatch to Celery background worker to offload OCR/Neo4j processing
            try:
                from app.infrastructure.queue.factory import get_scheduler
                get_scheduler().send_task(
                    "app.core.atlas.tasks.map_observed_ui",
                    args=(
                        image_source,
                        kwargs.get("device_id"),
                        platform,
                        ""
                    )
                )
                logger.debug(f"[VisionEngine] Dispatched Atlas background mapping for {image_source}")
            except Exception as ex:
                logger.debug(f"[VisionEngine] Failed to dispatch Celery task: {ex}")

        # 6. Publish Completion Event
        provider_name = provider.name if task != VisionTask.DETECT else "pipeline_manager"
        from app.core.vision.event.publishers import publish_vision_process_completed
        await publish_vision_process_completed(result, task.value, provider_name)

        return result


# Singleton instance
vision_engine = VisionEngine()
