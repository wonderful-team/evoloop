"""
Desktop Controller — Core macOS desktop automation.

Extracted from app.core.environment.tools.desktop to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/desktop.py thin wrapper).
"""

import asyncio
import logging
import math
import os
import time

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.environment.controllers.utils import (
    BatchExecutor,
    RecordingContext,
    resolve_element_alias,
)
from app.core.learning.trace.recorder import get_recorder
from app.core.vision.perceptions_formatter import PerceptionsFormatter
from app.infrastructure.drivers.macos import macos_driver
from app.infrastructure.vision import VisionTask, get_vision_router, vision_engine
from app.utils.controller_response import ControllerResponse

from ._app_mixin import DesktopAppMixin
from ._element_mixin import DesktopElementMixin
from ._interaction_mixin import DesktopInteractionMixin
from ._utils import _async_literal_eval
from ._verification_mixin import DesktopVerificationMixin

logger = logging.getLogger(__name__)

MAX_OUTPUT_LENGTH = 60000


# ─────────────────────────────────────────────
#  DesktopController
# ─────────────────────────────────────────────


class DesktopController(
    DesktopElementMixin,
    DesktopInteractionMixin,
    DesktopAppMixin,
    DesktopVerificationMixin,
):
    """
    Core macOS desktop automation logic.

    All methods are classmethods (stateless) — hardware state lives in
    the singleton `macos_driver` from infrastructure.
    """

    @classmethod
    async def execute(
        cls,
        action: str,
        x: int | None = None,
        y: int | None = None,
        element_name: str | None = None,
        target: str | None = None,
        element_role: str | None = None,
        text: str | None = None,
        key: str | None = None,
        app_name: str | None = None,
        script: str | None = None,
        region: str | None = None,
        interactive: bool = False,
        force_keystroke: bool = False,
        ocr: bool = False,
        actions: list[dict] | None = None,
        continue_on_error: bool = True,
        delay_ms: int = 300,
        direction: str | None = None,
        amount: int = 300,
        x2: int | None = None,
        y2: int | None = None,
        source_element: str | None = None,
        target_element: str | None = None,
        duration_ms: int = 500,
        role_filter: str | None = None,
        name_filter: str | None = None,
        max_depth: int | None = None,
        skip_recording: bool = False,
    ) -> str:
        try:
            element_name = resolve_element_alias(target, element_name)

            recorder = None
            if not skip_recording:
                session_id = ContextManager.get_var("thread_id")
                if session_id:
                    recorder = get_recorder(session_id)

            recording_ctx = RecordingContext(
                platform="macos",
                recorder=recorder,
                screenshot_actions=("click", "double_click", "type_text", "key_press", "open_app", "drag_drop")
                if not skip_recording else (),
            )

            _cached_app_info = None

            async def _get_cached_app_info():
                nonlocal _cached_app_info
                if _cached_app_info is None:
                    _cached_app_info = await asyncio.to_thread(macos_driver.get_current_app)
                return _cached_app_info

            async def _record(action_type: str, params: dict):
                async def screenshot_fn():
                    return await asyncio.to_thread(macos_driver.screenshot)

                async def context_fn():
                    app_info = await _get_cached_app_info()
                    return {
                        "app": app_info.get("name"),
                        "bundle_id": app_info.get("bundle_id"),
                    }

                await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

            # ── Shared context ─────────────────────────────────────────────
            from app.core.file import cleanup_file
            from app.utils.template import render_template

            ctx = {
                "recording_func": _record,
                "get_cached_app_info": _get_cached_app_info,
                "x": x, "y": y, "x2": x2, "y2": y2,
                "element_name": element_name,
                "element_role": element_role,
                "text": text,
                "key": key,
                "app_name": app_name,
                "script": script,
                "region": region,
                "force_keystroke": force_keystroke,
                "ocr": ocr,
                "actions": actions,
                "continue_on_error": continue_on_error,
                "delay_ms": delay_ms,
                "direction": direction,
                "amount": amount,
                "source_element": source_element,
                "target_element": target_element,
                "duration_ms": duration_ms,
                "role_filter": role_filter,
                "name_filter": name_filter,
                "max_depth": max_depth,
            }

            # ── Inline actions (need full setup context) ──────────────────
            if action == "screenshot":
                app_info = await _get_cached_app_info()
                bundle_id = app_info.get("bundle_id")

                region_offset_x, region_offset_y = 0, 0
                if region is None:
                    if settings.ENABLE_PARTIAL_SCREENSHOT:
                        bounds = app_info.get("bounds")
                        if bounds:
                            region = bounds
                            logger.info(f"[Desktop] Auto-capturing current window region: {region}")

                if region:
                    try:
                        rx, ry, _, _ = map(int, region.split(","))
                        region_offset_x, region_offset_y = rx, ry
                    except ValueError:
                        pass

                filepath = await asyncio.to_thread(
                    macos_driver.screenshot,
                    region=region,
                    interactive=interactive,
                    purpose="temp",
                    bundle_id=bundle_id,
                )
                result_msg = ControllerResponse.screenshot_result(success=True, filename=filepath)
                if ocr:
                    try:
                        ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
                        if ocr_result.success and ocr_result.elements:
                            elements_for_prompt = []
                            for el in ocr_result.elements:
                                el_dict = el.model_dump()
                                if region_offset_x or region_offset_y:
                                    el_dict["x"] = el.x + region_offset_x
                                    el_dict["y"] = el.y + region_offset_y
                                    el_dict["relative_x"] = el.x
                                    el_dict["relative_y"] = el.y
                                elements_for_prompt.append(el_dict)

                            if region_offset_x or region_offset_y:
                                result_msg += f"\n\n> [!NOTE]\n> Screenshot region: {region}\n> OCR coordinates are converted to screen coordinates."

                            result_msg += "\n\n" + render_template(
                                "core/vision/ocr_results.prompt.j2",
                                platform="macos",
                                elements=elements_for_prompt,
                                total_count=len(ocr_result.elements),
                            )
                        else:
                            result_msg += "\n\n" + ControllerResponse.error("OCR requested but no text detected.")
                    except Exception as e:
                        result_msg += "\n\n" + ControllerResponse.error("OCR Error.", details=str(e))
                return result_msg

            # ── Dispatch to mixin handlers ────────────────────────────────
            if action in ("click", "double_click", "type_text", "key_press", "scroll", "drag_drop"):
                result = await cls._handle_interaction(action, **ctx)
                if result is not None:
                    return result

            if action in ("get_info", "list_apps", "get_active_app", "open_app", "applescript"):
                result = await cls._handle_app(action, **ctx)
                if result is not None:
                    return result

            # ── Inline actions (need local imports / full context) ────────
            if action == "batch":
                if not actions:
                    return ControllerResponse.missing_param("actions")
                batch_start = time.time()
                executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)

                async def _exec_action(action_dict: dict) -> str:
                    params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
                    return await cls.execute(action=action_dict.get("action", "unknown"), **params)

                await executor.execute(actions, _exec_action)
                return executor.format_summary(time.time() - batch_start)

            elif action == "dump_ui":
                try:
                    raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
                    if not raw_tree or "Error" in raw_tree:
                        return ControllerResponse.error(f"Failed to dump Accessibility Tree: {raw_tree}")
                    elements = await _async_literal_eval(raw_tree.replace("missing value", "None"))
                    if not isinstance(elements, list):
                        return ControllerResponse.error("AX Tree format unexpected.")

                    filtered_elements = elements
                    if max_depth is not None:

                        def _truncate_depth(nodes, depth=0):
                            if depth >= max_depth:
                                return [{k: v for k, v in n.items() if k != "children"} for n in nodes]
                            result = []
                            for n in nodes:
                                item = dict(n)
                                if "children" in item:
                                    item["children"] = _truncate_depth(item["children"], depth + 1)
                                result.append(item)
                            return result

                        filtered_elements = _truncate_depth(elements)
                    if role_filter:
                        filtered_elements = [el for el in filtered_elements if role_filter.lower() in str(el.get("role", "")).lower()]
                    if name_filter:
                        filtered_elements = [el for el in filtered_elements if name_filter.lower() in str(el.get("name", "")).lower()]

                    try:
                        return "\n\n" + render_template(
                            "core/vision/ocr_results.prompt.j2",
                            platform="macos",
                            elements=[{**el, "bounds": el.get("bounds", [])} for el in filtered_elements[:100]],
                            total_count=len(filtered_elements)
                        )
                    except Exception as e:
                        logger.exception(f"Failed to render OCR results template: {e}")
                        return PerceptionsFormatter.ui_elements(filtered_elements, max_items=50)

                except Exception as e:
                    return ControllerResponse.error("dump_ui failed.", details=str(e))

            elif action == "gui_extract":
                filepath = await asyncio.to_thread(macos_driver.screenshot, region=region)
                if not filepath or not os.path.exists(filepath):
                    return ControllerResponse.error("Failed to capture screenshot for GUI extraction.")

                try:
                    router = get_vision_router()
                    provider = await router.get_provider(VisionTask.OCR)
                    if not provider:
                        return ControllerResponse.error("No OCR provider available for desktop GUI extraction.")

                    result = await provider.process(VisionTask.OCR, filepath)
                    if not result.success or not result.elements:
                        return ""

                    target_x = x if x is not None else 0.5
                    target_y = y if y is not None else 0.5
                    best_match, min_dist = None, float("inf")

                    for el in result.elements:
                        dist = math.sqrt((el.x - (target_x if target_x > 1 else target_x * 1000))**2 +
                                         (el.y - (target_y if target_y > 1 else target_y * 1000))**2)
                        if dist < min_dist:
                            min_dist, best_match = dist, el.text

                    return best_match or ""
                finally:
                    cleanup_file(filepath)

            else:
                return ControllerResponse.error(f"Unknown action '{action}'.")

        except PermissionError as e:
            return ControllerResponse.error(
                "PERMISSION ERROR",
                details=str(e),
                note="Please grant Accessibility access to the terminal/application running this backend.",
            )
        except Exception as e:
            logger.exception(f"Desktop control error: {e}")
            return ControllerResponse.error("Desktop action failed.", details=str(e))
