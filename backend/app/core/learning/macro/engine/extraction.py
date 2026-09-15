import json
import logging
import os
import re

import app.core.learning.constants as _mc
from app.core.learning.macro.schemas import MacroSource
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


def _unwrap_controller_value(res):
    """Strip the ✅/❌ ControllerResponse envelope, keeping the details payload.

    Browser extraction actions render `✅ <message>\\n\\n<details>`; macros need
    the raw value (an id, a price) for downstream {{key}} references. ❌ means
    the extraction failed -> None, so unresolved placeholders trip the
    navigate guard instead of fabricating a garbage URL.
    """
    if not isinstance(res, str):
        return res
    if res.startswith("❌"):
        return None
    if res.startswith("JS result: "):
        return res[len("JS result: ") :]
    if res.startswith("✅"):
        return res.split("\n\n", 1)[1].strip() if "\n\n" in res else ""
    return res


class ExtractionMixin:
    @classmethod
    async def handle_extraction(
        cls, thread_id, step, selector, payload, params, extracted_data
    ):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.environment.controllers.mobile import MobileController

        key = cls._inject_params(step.key, params) or "data"
        extract_type = step.extract_type or step.event_type

        desc = f"Extract '{key}' from {selector}"
        await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)

        if step.source == MacroSource.DOM:
            call_kwargs = {"action": extract_type, "selector": selector}
            if extract_type == _mc.GET_ATTRIBUTE and "attribute" in payload:
                call_kwargs["attribute"] = payload["attribute"]
            elif extract_type in (_mc.RUN_JS, _mc.EVALUATE) and (
                "script" in payload or "expression" in payload
            ):
                call_kwargs["action"] = _mc.RUN_JS
                call_kwargs["script"] = payload.get("script") or payload.get(
                    "expression"
                )
            if payload.get("state"):
                call_kwargs["state"] = payload["state"]

            res = await BrowserController.execute(**call_kwargs)
            if (
                extract_type in (_mc.RUN_JS, _mc.EVALUATE)
                and isinstance(res, str)
                and res.startswith("❌")
            ):
                raise ValueError(res)
            if extract_type == _mc.SCREENSHOT:
                match = re.search(r"(/.*\.png)", str(res))
                extracted_data[key] = match.group(1) if match else res
            else:
                res = _unwrap_controller_value(res)
                try:
                    if isinstance(res, str) and (
                        res.startswith("[") or res.startswith("{")
                    ):
                        extracted_data[key] = json.loads(res)
                    else:
                        extracted_data[key] = res
                except Exception as e:
                    logger.exception(f"Macro extraction error: {e}")
                    extracted_data[key] = res

        elif step.source in (
            MacroSource.MOBILE,
            MacroSource.GLOBAL,
            MacroSource.DESKTOP,
        ):
            if extract_type == _mc.GUI_EXTRACT:
                await cls._handle_gui_extract(
                    thread_id, step, selector, payload, params, extracted_data
                )
                return

            if extract_type == _mc.DUMP_UI:
                if step.source == MacroSource.DESKTOP:
                    res = await DesktopController.execute(action=_mc.DUMP_UI)
                else:
                    res = await MobileController.execute(action=_mc.DUMP_UI)
                extracted_data[key] = res
            elif extract_type == _mc.SCREENSHOT:
                if step.source == MacroSource.DESKTOP:
                    res = await DesktopController.execute(
                        action=_mc.SCREENSHOT, region=payload.get("region")
                    )
                else:
                    res = await MobileController.execute(
                        action=_mc.SCREENSHOT, region=payload.get("region")
                    )

                match = re.search(r"(/.*\.png)", str(res))
                filepath = match.group(1) if match else str(res)
                if selector and filepath.endswith(".png"):
                    if step.source == MacroSource.MOBILE:
                        filepath = await cls._crop_mobile_screenshot(filepath, selector)
                extracted_data[key] = filepath

    @classmethod
    async def _handle_gui_extract(
        cls, thread_id, step, selector, payload, params, extracted_data
    ):
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.environment.controllers.mobile import MobileController

        key = cls._inject_params(step.key, params) or "extracted_text"
        pos = payload.get("relative_position") or {
            "x": payload.get("x", 0.5),
            "y": payload.get("y", 0.5),
        }
        region = payload.get("region")

        try:
            if step.source == MacroSource.DESKTOP:
                res = await DesktopController.execute(
                    action=_mc.GUI_EXTRACT,
                    x=pos.get("x"),
                    y=pos.get("y"),
                    region=region,
                )
                extracted_data[key] = res
            elif step.source == MacroSource.MOBILE:
                res = await MobileController.execute(
                    action=_mc.GUI_EXTRACT,
                    x=pos.get("x"),
                    y=pos.get("y"),
                    region=region,
                    extraction_method=payload.get("extraction_method"),
                )

                if isinstance(res, str) and (
                    res.startswith("[") or res.startswith("{")
                ):
                    try:
                        extracted_data[key] = json.loads(res)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        extracted_data[key] = res
                else:
                    extracted_data[key] = res
            else:
                extracted_data[key] = None
        except Exception as e:
            logger.exception(f"GUI Extract OCR failed: {e}")
            extracted_data[key] = None

    @classmethod
    async def _crop_mobile_screenshot(cls, filepath, selector):
        try:
            from PIL import Image

            from app.infrastructure.vision.providers.native.android_a11y import (
                android_a11y_provider,
            )
            from app.infrastructure.vision.types import VisionTask

            def _norm(t):
                return re.sub(r"\s+", "", t).lower() if t else ""

            a11y_res = await android_a11y_provider.process(
                VisionTask.DETECT, "", device_id=None
            )

            if a11y_res.success:
                target_norm = _norm(selector)
                for el in a11y_res.elements:
                    if _norm(el.text) == target_norm or target_norm in _norm(
                        el.metadata.get("resource_id", "")
                    ):
                        bounds = (
                            el.x - el.width // 2,
                            el.y - el.height // 2,
                            el.x + el.width // 2,
                            el.y + el.height // 2,
                        )
                        with Image.open(filepath) as img:
                            cropped = img.crop(bounds)
                            new_path = filepath.replace(
                                ".png", f"_crop_{_norm(selector)[:15]}.png"
                            )
                            cropped.save(new_path)
                            os.remove(filepath)
                            return new_path
        except Exception as e:
            logger.warning(f"MacroEngine cropping failed: {e}", exc_info=True)
        return filepath
