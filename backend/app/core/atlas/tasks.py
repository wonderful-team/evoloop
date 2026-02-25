import asyncio
import logging
from typing import Any, List

from celery import shared_task

from app.core.environment.events import UiTreeObservedEvent, event_bus
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


def run_async(coro):
    """Utility to run async coroutines in sync Celery workers."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # Fallback for cases where a loop is already running (e.g. weird pool configs)
        if "already running" in str(e).lower():
            try:
                loop = asyncio.get_event_loop()
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(coro)
            except Exception:
                pass
        raise e


@shared_task(name="app.core.atlas.tasks.map_observed_ui")
def map_observed_ui_task(
    image_source: str,
    device_id: str | None,
    platform: str,
    scene_hash: str = ""
):
    """
    Background Celery task to perform UI perception and map it to the App Atlas.
    Decouples heavy OCR/Perception from the Agent's main loop.
    """
    logger.info(f"[AtlasTask] Starting background mapping for {image_source} (Platform: {platform})")
    
    async def _execute():
        try:
            from app.core.vision.pipeline.manager import pipeline_manager
            
            # 1. Run perception pipeline
            elements, _ = await pipeline_manager.perceive(
                screenshot_path=image_source,
                device_id=device_id
            )

            if not elements:
                logger.debug("[AtlasTask] No elements detected, skipping mapping.")
                return

            # 2. Get current app context
            # Caching in macos_driver (0.5s) helps here if called rapidly
            app_info = macos_driver.get_current_app()

            # 3. Map vision elements to Atlas semantic format
            atlas_elements = []
            for el in elements:
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

            # 4. Trigger the Atlas engine via the event bus
            # In a Celery worker, we can directly call the engine if needed, 
            # but using events preserves the modular architecture.
            await event_bus.publish(UiTreeObservedEvent(
                platform=platform,
                bundle_id=app_info.get("bundle_id", "unknown"),
                window_title=app_info.get("title", "unknown"),
                elements=atlas_elements,
                screenshot_hash=scene_hash
            ))
            
            logger.info(f"[AtlasTask] Successfully mapped {len(atlas_elements)} elements for {app_info.get('bundle_id')}")
            
        except Exception as e:
            logger.error(f"[AtlasTask] Background mapping failed: {e}", exc_info=True)

    return run_async(_execute())
