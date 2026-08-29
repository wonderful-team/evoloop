"""
Mobile controller mixin — advanced actions (screenshot, push/pull, intent_flow, etc.).
"""

import asyncio
import json
import logging
import math
import os
import time

from app.core.file import cleanup_file
from app.core.vision.perceptions_formatter import PerceptionsFormatter
from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.vision import VisionTask, get_vision_router, vision_engine
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


class MobileAdvancedMixin:
    @classmethod
    async def _handle_advanced(cls, action: str, **ctx) -> str | None:
        finish_action = ctx["finish_action"]
        _get_effective_package = ctx["_get_effective_package"]
        resolve_element = ctx["resolve_element"]
        validate_outcome = ctx["validate_outcome"]
        check_sentinel = ctx["check_sentinel"]
        trigger_atlas_harvest = ctx["trigger_atlas_harvest"]
        device_id = ctx.get("device_id")
        x = ctx.get("x")
        y = ctx.get("y")
        text = ctx.get("text")
        region = ctx.get("region")
        ocr = ctx.get("ocr", False)
        local_path = ctx.get("local_path")
        remote_path = ctx.get("remote_path")
        timeout = ctx.get("timeout", 8.0)
        intents = ctx.get("intents")
        after_timestamp = ctx.get("after_timestamp")
        kwargs = ctx.get("kwargs", {})

        if action == "list_devices":
            devices = await asyncio.to_thread(adb_driver.list_devices)
            if not devices:
                return ControllerResponse.error(
                    "No Android devices connected.",
                    note="Please enable USB debugging and accept the authorization prompt.",
                )
            return PerceptionsFormatter.android_devices(devices)

        elif action == "screenshot":
            package = await _get_effective_package()
            filepath = await asyncio.to_thread(
                adb_driver.screenshot, device_id=device_id, bundle_id=package
            )

            from PIL import Image

            if region and filepath and os.path.exists(filepath):
                try:
                    coords = [int(c.strip()) for c in region.split(",")]
                    if len(coords) == 4:
                        rx, ry, rw, rh = coords
                        with Image.open(filepath) as img:
                            img_w, img_h = img.size
                            box = (
                                max(0, rx),
                                max(0, ry),
                                min(img_w, rx + rw),
                                min(img_h, ry + rh),
                            )
                            cropped = img.crop(box)
                            cropped.save(filepath)
                            logger.info(
                                f"[Mobile] Screenshot cropped to region: {region}"
                            )
                except Exception as e:
                    logger.warning(
                        f"[Mobile] Region cropping failed: {e}", exc_info=True
                    )

            result_msg = ControllerResponse.screenshot_result(
                success=True, filename=filepath
            )
            if ocr:
                try:
                    ocr_res = await vision_engine.process(
                        VisionTask.OCR, filepath, on_android=True, device_id=device_id
                    )
                    if ocr_res.success and ocr_res.elements:
                        from app.utils.template import render_template

                        result_msg += "\n\n" + render_template(
                            "core/vision/ocr_results.prompt.j2",
                            platform="android",
                            elements=[
                                {
                                    "role": el.metadata.get("class", "Unknown"),
                                    "name": el.text,
                                    "bounds": f"({el.x}, {el.y})",
                                    "path": el.metadata.get("resource_id", ""),
                                }
                                for el in ocr_res.elements
                            ],
                            total_count=len(ocr_res.elements),
                        )
                    else:
                        result_msg += "\n\n" + ControllerResponse.error(
                            "OCR requested but no text detected."
                        )
                except Exception as e:
                    result_msg += "\n\n" + ControllerResponse.error(
                        "OCR Error.", details=str(e)
                    )
            return await finish_action(result_msg)

        elif action == "push":
            if not local_path or not remote_path:
                return ControllerResponse.error(
                    "'local_path' and 'remote_path' are required for push."
                )
            await asyncio.to_thread(
                adb_driver.push, local_path, remote_path, device_id=device_id
            )
            return ControllerResponse.success(
                "Pushed file.", details=f"{local_path} -> {remote_path}"
            )

        elif action == "pull":
            if not local_path or not remote_path:
                return ControllerResponse.error(
                    "'local_path' and 'remote_path' are required for pull."
                )
            await asyncio.to_thread(
                adb_driver.pull, remote_path, local_path, device_id=device_id
            )
            return ControllerResponse.success(
                "Pulled file.", details=f"{remote_path} -> {local_path}"
            )

        elif action == "dump_ui":
            xml = await asyncio.to_thread(adb_driver.dump_ui, device_id=device_id)
            return ControllerResponse.success("UI Hierarchy Dump", details=xml)

        elif action == "intent_flow":
            if not intents:
                return "Error: 'intents' list is required for intent_flow."
            steps_done = 0
            base_pkg = await _get_effective_package()

            async def _execute_intent_step(it: dict) -> str | None:
                act = it.get("action")
                tgt = it.get("target") or it.get("element_name")

                if act == "click" and tgt:
                    resolved = await resolve_element(
                        tgt, expected_pkg=base_pkg, timeout_val=timeout
                    )
                    if isinstance(resolved, str):
                        return resolved
                    await asyncio.to_thread(
                        adb_driver.tap,
                        resolved["x"],
                        resolved["y"],
                        device_id=device_id,
                    )
                    if not await validate_outcome(base_pkg):
                        await check_sentinel(base_pkg)
                elif act == "input" and it.get("text"):
                    if tgt:
                        resolved = await resolve_element(
                            tgt, expected_pkg=base_pkg, timeout_val=timeout
                        )
                        if isinstance(resolved, str):
                            return resolved
                        await asyncio.to_thread(
                            adb_driver.tap,
                            resolved["x"],
                            resolved["y"],
                            device_id=device_id,
                        )
                    await asyncio.to_thread(
                        adb_driver.input_text, it["text"], device_id=device_id
                    )
                return None

            for it in intents:
                if error := await _execute_intent_step(it):
                    return error
                steps_done += 1

            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(
                f"Successfully executed intent flow with {steps_done} steps."
            )

        elif action == "read_sms":
            pattern = text if text else r"\d{4,6}"
            wait_time = int(timeout) if timeout else 30
            logger.info(
                f"Polling SMS inbox for pattern '{pattern}' up to {wait_time}s..."
                + (f" (after timestamp: {after_timestamp})" if after_timestamp else "")
            )
            messages = await asyncio.to_thread(
                adb_driver.read_sms,
                regex_pattern=pattern,
                timeout=wait_time,
                device_id=device_id,
                after_timestamp=after_timestamp,
            )
            if not messages:
                return await finish_action(
                    f"No SMS matching pattern '{pattern}' received within {wait_time} seconds.",
                    success=False,
                )
            latest = messages[0]
            if latest.get("extract"):
                return await finish_action(
                    f"SMS Received! Match: {latest['extract']}",
                    note=f"Full Body: {latest['body']}",
                )
            return await finish_action(f"SMS Received: {latest['body']}")

        elif action == "get_clipboard":
            clip_text = await asyncio.to_thread(
                adb_driver.get_clipboard, device_id=device_id
            )
            return await finish_action(
                f"Clipboard content: {clip_text}"
                if clip_text
                else "Clipboard is empty."
            )

        elif action == "gui_extract":
            from PIL import Image

            def _crop_screenshot(filepath: str, region_str: str) -> bool:
                try:
                    coords = [int(c.strip()) for c in region_str.split(",")]
                    if len(coords) != 4:
                        return False
                    rx, ry, rw, rh = coords
                    with Image.open(filepath) as img:
                        box = (
                            max(0, rx),
                            max(0, ry),
                            min(img.size[0], rx + rw),
                            min(img.size[1], ry + rh),
                        )
                        img.crop(box).save(filepath)
                    return True
                except Exception:
                    return False

            def _group_elements_to_rows(elements, screen_height: int = 2400):
                threshold = screen_height * 0.05
                sorted_elements = sorted(elements, key=lambda e: e.y)
                rows, current_row, last_y = [], [], -float("inf")

                for el in sorted_elements:
                    if abs(el.y - last_y) > threshold:
                        if current_row:
                            avg_x = sum(e.x for e in current_row) / len(current_row)
                            avg_y = sum(e.y for e in current_row) / len(current_row)
                            rows.append(
                                {
                                    "text": " | ".join(
                                        [
                                            e.text
                                            for e in sorted(
                                                current_row, key=lambda x: x.x
                                            )
                                        ]
                                    ),
                                    "x": int(avg_x),
                                    "y": int(avg_y),
                                }
                            )
                        current_row, last_y = [el], el.y
                    else:
                        current_row.append(el)

                if current_row:
                    avg_x = sum(e.x for e in current_row) / len(current_row)
                    avg_y = sum(e.y for e in current_row) / len(current_row)
                    rows.append(
                        {
                            "text": " | ".join(
                                [e.text for e in sorted(current_row, key=lambda x: x.x)]
                            ),
                            "x": int(avg_x),
                            "y": int(avg_y),
                        }
                    )
                return rows

            cache_key = device_id or "default"
            now = time.time()
            cached_path, ts = cls._screenshot_cache.get(cache_key, (None, 0))

            if (
                cached_path
                and os.path.exists(cached_path)
                and (now - ts < cls._screenshot_cache_ttl_ms / 1000.0)
            ):
                filepath = cached_path
                logger.debug(
                    f"[Mobile] Reusing cached screenshot for GUI extraction: {filepath}"
                )
            else:
                filepath = await asyncio.to_thread(
                    adb_driver.screenshot, device_id=device_id
                )
                if filepath:
                    cls._screenshot_cache[cache_key] = (filepath, now)

            if region and filepath:
                _crop_screenshot(filepath, region)

            if not filepath or not os.path.exists(filepath):
                return ControllerResponse.error(
                    "Failed to capture screenshot for GUI extraction."
                )

            try:
                router = get_vision_router()
                provider = await router.get_provider(
                    VisionTask.OCR, on_android=True, device_id=device_id
                )
                if not provider:
                    return ControllerResponse.error(
                        "No OCR provider available for mobile GUI extraction."
                    )

                result = await provider.process(VisionTask.OCR, filepath)
                if not result.success or not result.elements:
                    return (
                        "[]"
                        if kwargs.get("extraction_method") == "list"
                        or "loop" in str(kwargs)
                        else ""
                    )

                is_list_request = kwargs.get("extraction_method") in (
                    "list",
                    "ocr_region",
                )

                if is_list_request:
                    _, screen_height = await asyncio.to_thread(
                        adb_driver.get_screen_size, device_id=device_id
                    )
                    rows = _group_elements_to_rows(result.elements, screen_height)
                    return (
                        json.dumps(rows, ensure_ascii=False)
                        if kwargs.get("extraction_method") == "list"
                        else rows
                    )

                target_x = x if x is not None else 0.5
                target_y = y if y is not None else 0.5
                best_match, min_dist = None, float("inf")

                for el in result.elements:
                    dist = math.sqrt(
                        (el.x - (target_x if target_x > 1 else target_x * 1000)) ** 2
                        + (el.y - (target_y if target_y > 1 else target_y * 1000)) ** 2
                    )
                    if dist < min_dist:
                        min_dist, best_match = dist, el.text

                return best_match or ""
            finally:
                current_cache_path, _ = cls._screenshot_cache.get(cache_key, (None, 0))
                if filepath and filepath != current_cache_path:
                    cleanup_file(filepath)

        return None
