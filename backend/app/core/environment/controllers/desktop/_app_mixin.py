"""
Desktop controller mixin — app management actions (open_app, applescript, info).
"""
import asyncio
import logging

import markdownify

from app.core.atlas import atlas_engine, get_bundle_id
from app.core.environment.controllers.utils import truncate_output
from app.infrastructure.drivers.macos import macos_driver
from app.utils.controller_response import ControllerResponse

from ._utils import _trigger_atlas_harvest_macos

logger = logging.getLogger(__name__)

MAX_OUTPUT_LENGTH = 60000


class DesktopAppMixin:

    @classmethod
    async def _handle_app(cls, action: str, **ctx) -> str | None:
        recording_func = ctx["recording_func"]
        app_name = ctx.get("app_name")
        script = ctx.get("script")

        if action == "get_info":
            info = await asyncio.to_thread(macos_driver.get_system_info)
            return ControllerResponse.success("System Info", details=str(info))

        elif action == "list_apps":
            apps = await asyncio.to_thread(macos_driver.list_installed_apps)
            return ControllerResponse.success("Installed Apps", details=str(apps))

        elif action == "get_active_app":
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            return ControllerResponse.success("Active Application", details=str(app_info))

        elif action == "open_app":
            if not app_name:
                return ControllerResponse.missing_param("app_name")
            bundle_id = await get_bundle_id(app_name)
            is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos") if bundle_id else False
            app_type_str = "DYNAMIC" if is_dynamic else "STATIC"
            result = await asyncio.to_thread(macos_driver.open_app, app_name)
            if is_dynamic:
                strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                if strategy:
                    logger.info(f"[Desktop] Preloaded strategy for {bundle_id}")
            else:
                asyncio.create_task(_trigger_atlas_harvest_macos(bundle_id))
            await recording_func("open_app", {"app_name": app_name, "bundle_id": bundle_id})
            if "Error" not in result:
                return ControllerResponse.success(result, note=f"App Type: {app_type_str}")
            return ControllerResponse.error(result)

        elif action == "applescript":
            if not script:
                return ControllerResponse.missing_param("script")
            output = await asyncio.to_thread(macos_driver.run_applescript, script)
            if output:
                if "</div>" in output or "</body>" in output or "<br>" in output:
                    try:
                        md_output = markdownify.markdownify(output, heading_style="ATX")
                        if md_output.strip():
                            output = f"[Converted from HTML to Markdown]\n{md_output}"
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                        logger.warning(f"Markdown conversion failed: {e}")
                output = truncate_output(output, MAX_OUTPUT_LENGTH)
            if output:
                return ControllerResponse.success("AppleScript executed.", details=f"Output: {output}")
            return ControllerResponse.success("AppleScript executed successfully.")

        return None
