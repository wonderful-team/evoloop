import asyncio
import logging
import os

from app.core.atlas.models import AtlasApp
from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.drivers.macos import macos_driver

# Unified task queue (Huey in embedded mode, Celery in full mode)
from app.infrastructure.queue.factory import shared_task
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


def run_async(coro):
    """Utility to run async coroutines in sync Celery workers."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # Fallback for cases where a loop is already running (e.g. weird pool configs)
        if "already running" in str(e).lower():
            try:
                loop = asyncio.get_running_loop()
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(coro)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
        raise e


@shared_task(name="app.core.atlas.tasks.map_observed_ui")
def map_observed_ui_task(
    image_source: str,
    device_id: str | None,
    platform: str,
    scene_hash: str = "",
    bundle_id: str | None = None  # Pre-computed bundle_id from caller
):
    """
    Background Celery task to perform UI perception and map it to the App Atlas.
    Decouples heavy OCR/Perception from the Agent's main loop.
    """
    logger.info(f"[AtlasTask] Starting background mapping for {image_source} (Platform: {platform})")

    async def _execute():
        try:
            from app.infrastructure.vision.pipeline.manager import pipeline_manager

            # 1. Run perception pipeline
            elements, _ = await pipeline_manager.perceive(
                screenshot_path=image_source,
                device_id=device_id
            )

            if not elements:
                logger.debug("[AtlasTask] No elements detected, skipping mapping.")
                return

            # 2. Get current app context
            # Use provided bundle_id if available, otherwise detect from system
            detected_bundle_id = None
            if platform == "macos":
                app_info = macos_driver.get_current_app()
                detected_bundle_id = app_info.get("bundle_id", "unknown")
                window_title = app_info.get("title", "unknown")
                version_hash = ""
            elif platform == "android":
                app_info = adb_driver.get_current_app(device_id=device_id)
                detected_bundle_id = app_info.get("package", "unknown")
                window_title = app_info.get("activity", "unknown")

                # Version Awareness
                version_hash = ""
                # Use detected bundle_id for version lookup if no explicit bundle_id provided
                version_lookup_id = bundle_id or detected_bundle_id
                if version_lookup_id and version_lookup_id != "unknown":
                    try:
                        pkg_meta = adb_driver.get_package_info(version_lookup_id, device_id=device_id)
                        ver_name = str(pkg_meta.get("version_name", "0"))
                        upd_time = str(pkg_meta.get("last_update_time", "0"))

                        # Compute stable version hash using AtlasApp's logic
                        dummy_app = AtlasApp(app_name=version_lookup_id, bundle_id=version_lookup_id, platform="android")
                        version_hash = dummy_app.compute_version_hash(ver_name, upd_time)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as ve:
                        logger.warning(f"[AtlasTask] Failed to get version info for {version_lookup_id}: {ve}")
            else:
                detected_bundle_id = "unknown"
                window_title = "unknown"
                version_hash = ""

            # Priority: use provided bundle_id, fallback to detected
            final_bundle_id = bundle_id or detected_bundle_id or "unknown"

            # Warn if there's a mismatch between provided and detected
            if bundle_id and detected_bundle_id and bundle_id != detected_bundle_id:
                logger.warning(
                    f"[AtlasTask] Bundle ID mismatch: "
                    f"provided={bundle_id}, detected={detected_bundle_id}. "
                    f"Using provided: {final_bundle_id}"
                )

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
                    },
                    # Phase 5/6: Structured IDs
                    "os_identifier": el.metadata.get("resource_id") or el.metadata.get("view_id") or el.metadata.get("ax_path")
                })

            # 4. Use temp screenshot directly (no copy to atlas for efficiency)
            # The temp screenshot will be auto-cleaned after retention period
            # Atlas only stores structured element data, not raw images
            stored_path = image_source if image_source and os.path.exists(image_source) else None

            # 5. Trigger the Atlas engine via the event bus
            from app.core.environment.event.publishers import publish_ui_tree_observed
            await publish_ui_tree_observed(
                platform=platform,
                bundle_id=final_bundle_id,
                window_title=window_title,
                elements=atlas_elements,
                screenshot_hash=scene_hash,
                version_hash=version_hash,
            )

            logger.info(f"[AtlasTask] Successfully mapped {len(atlas_elements)} elements for {final_bundle_id}")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[AtlasTask] Background mapping failed: {e}", exc_info=True)

    async def _run_with_flush():
        try:
            await _execute()
        finally:
            await flush_loop_bound_resources()

    return run_async(_run_with_flush())
