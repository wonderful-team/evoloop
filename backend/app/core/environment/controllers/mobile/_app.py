"""
Mobile controller mixin — app management actions (open_app, info, list_apps).
"""
import asyncio
import logging

from app.core.atlas import atlas_engine
from app.infrastructure.drivers.adb import adb_driver
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


class MobileAppMixin:

    @classmethod
    async def _handle_app(cls, action: str, **ctx) -> str | None:
        recording_func = ctx["recording_func"]
        trigger_atlas_harvest = ctx["trigger_atlas_harvest"]
        device_id = ctx.get("device_id")
        text = ctx.get("text")
        kwargs = ctx.get("kwargs", {})

        if action == "get_info":
            info = await asyncio.to_thread(adb_driver.get_system_info, device_id=device_id)
            return ControllerResponse.success("System Info", details=str(info))

        elif action == "list_apps":
            apps = await asyncio.to_thread(adb_driver.list_installed_apps, device_id=device_id)
            return ControllerResponse.success("Installed Apps", details=str(apps))

        elif action == "open_app":
            if not text:
                return ControllerResponse.missing_param("text")

            if kwargs.get("force_stop") or kwargs.get("restart", False):
                await asyncio.to_thread(adb_driver.force_stop, text, device_id=device_id)

            is_dynamic = await atlas_engine.is_dynamic_app(text, "android")
            app_type_str = "DYNAMIC" if is_dynamic else "STATIC"

            await asyncio.to_thread(adb_driver.launch_app, text, device_id=device_id)

            async def _preload_atlas_data():
                try:
                    if is_dynamic:
                        strategy = await atlas_engine.get_app_strategy(text, "android")
                        if strategy:
                            logger.info(f"[Mobile] Atlas strategy preloaded for {text}")
                    else:
                        await trigger_atlas_harvest(bundle_id=text)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                    logger.debug(f"[Mobile] Atlas preload for {text} (non-critical): {e}")

            asyncio.create_task(_preload_atlas_data())

            await recording_func("open_app", {"package": text, "type": app_type_str})
            return ControllerResponse.success(f"Opened: {text}", note=f"App Type: {app_type_str}")

        return None
