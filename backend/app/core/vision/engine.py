import asyncio
import logging
import time
from typing import Optional

from app.core.vision.router import VisionRouter
from app.core.vision.types import VisionResult, VisionTask
from app.core.vision.events import VisionProcessStartedEvent, VisionProcessCompletedEvent
from app.core.events.base import system_bus
from app.core.environment.events import event_bus, UiTreeObservedEvent
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


class VisionEngine:
    """
    Core facade for the Vision Subsystem.
    Provides a unified entry point for all vision-related operations.
    """

    def __init__(self):
        self.router = VisionRouter()

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VisionResult:
        """
        Main entry point to process any vision task.
        """
        start_time = time.time()
        
        # 1. Publish Start Event
        await system_bus.publish(VisionProcessStartedEvent(
            data={"task": task.value, "source": image_source}
        ))

        # Specialized Logic: DETECTION (Multiple Providers)
        if task == VisionTask.DETECT:
            from app.core.vision.pipeline.manager import pipeline_manager
            elements, compressed_path = await pipeline_manager.perceive(
                screenshot_path=image_source,
                device_id=kwargs.get("device_id"),
                use_cache=kwargs.get("use_cache", True)
            )
            result = VisionResult(
                task=task,
                success=True,
                elements=elements,
                screenshot_path=compressed_path or image_source,
                summary=f"Detected {len(elements)} items using PipelineManager."
            )

            # --- Passive Atlas Learning ---
            try:
                # 1. Get current context for metadata
                app_info = macos_driver.get_current_app()
                
                # 2. Publish to Awakening Event Bus for AppAtlasService to consume
                await event_bus.publish(UiTreeObservedEvent(
                    platform="macos",
                    bundle_id=app_info.get("bundle_id", "unknown"),
                    window_title=app_info.get("title", "unknown"),
                    elements=[e.to_dict() for e in elements],
                    screenshot_hash=kwargs.get("scene_hash", "")
                ))
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
        if task != VisionTask.DETECT and result.success:
            # Run background perception to feed the Atlas without blocking the response
            async def background_map():
                try:
                    from app.core.vision.pipeline.manager import pipeline_manager
                    # We use cached results if possible to avoid double processing
                    bg_elements, _ = await pipeline_manager.perceive(
                        screenshot_path=image_source,
                        device_id=kwargs.get("device_id"),
                        use_cache=True
                    )

                    if bg_elements:
                        app_info = macos_driver.get_current_app()

                        # Map vision elements to Atlas semantic format
                        atlas_elements = []
                        for el in bg_elements:
                            atlas_elements.append({
                                "role": el.metadata.get("role", "AXUnknown"),
                                "label": el.text,
                                "ax_path": el.metadata.get("ax_path", f"Unknown.{el.id}"),
                                "bounds": {
                                    "x": el.x - el.width // 2,
                                    "y": el.y - el.height // 2,
                                    "width": el.width,
                                    "height": el.height
                                }
                            })

                        await event_bus.publish(UiTreeObservedEvent(
                            platform="macos",
                            bundle_id=app_info.get("bundle_id", "unknown"),
                            window_title=app_info.get("title", "unknown"),
                            elements=atlas_elements,
                            screenshot_hash=kwargs.get("scene_hash", "")
                        ))
                except Exception as ex:
                    logger.debug(f"[VisionEngine] Background mapping failed: {ex}")

            asyncio.create_task(background_map())

        # 6. Publish Completion Event
        provider_name = provider.name if task != VisionTask.DETECT else "pipeline_manager"
        await system_bus.publish(VisionProcessCompletedEvent(
            result=result,
            data={"task": task.value, "provider": provider_name}
        ))
        
        return result


# Singleton instance
vision_engine = VisionEngine()
