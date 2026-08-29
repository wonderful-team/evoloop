"""
Mobile controller mixin — interaction actions (tap, swipe, scroll, input, etc.).
"""

import asyncio
import logging
import time

from app.infrastructure.drivers.adb import adb_driver
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


class MobileInteractionMixin:
    @classmethod
    async def _handle_interaction(cls, action: str, **ctx) -> str | None:
        _normalize_coordinates = ctx["_normalize_coordinates"]
        _resolve_with_fallback = ctx["_resolve_with_fallback"]
        _post_action_cleanup = ctx["_post_action_cleanup"]
        resolve_element = ctx["resolve_element"]
        _get_effective_package = ctx["_get_effective_package"]
        _get_current_package = ctx["_get_current_package"]
        device_id = ctx.get("device_id")
        element_name = ctx.get("element_name")
        element_role = ctx.get("element_role")
        x = ctx.get("x")
        y = ctx.get("y")
        x2 = ctx.get("x2")
        y2 = ctx.get("y2")
        text = ctx.get("text")
        keycode = ctx.get("keycode")
        duration_ms = ctx.get("duration_ms", 300)
        timeout = ctx.get("timeout", 8.0)
        fast_probe = ctx.get("fast_probe", False)
        direction = ctx.get("direction")
        scroll_amount = ctx.get("scroll_amount", "medium")
        kwargs = ctx.get("kwargs", {})

        if action in ("tap", "click"):
            base_pkg = await _get_effective_package()
            tx, ty = await _normalize_coordinates(x, y)
            if element_name:
                result = await _resolve_with_fallback(
                    element_name,
                    element_role,
                    tx,
                    ty,
                    timeout,
                    base_pkg,
                    fast_probe_enabled=fast_probe,
                )
                if isinstance(result, str):
                    return result
                tx, ty = result
            if tx is None or ty is None:
                return "Error: Coordinates or element_name required."
            await asyncio.to_thread(adb_driver.tap, tx, ty, device_id=device_id)
            msg = ControllerResponse.tap_result(tx, ty, element_name=element_name)
            return await _post_action_cleanup(
                "click", {"x": tx, "y": ty, "element_name": element_name}, msg
            )

        elif action == "long_press":
            base_pkg = await _get_effective_package()
            tx, ty = await _normalize_coordinates(x, y)
            if element_name:
                result = await _resolve_with_fallback(
                    element_name,
                    element_role,
                    tx,
                    ty,
                    timeout,
                    base_pkg,
                    fast_probe_enabled=fast_probe,
                )
                if isinstance(result, str):
                    return result
                tx, ty = result
            if tx is None or ty is None:
                return "Error: Coordinates or element_name required."
            press_duration = duration_ms if duration_ms > 300 else 800
            await asyncio.to_thread(
                adb_driver.long_press,
                tx,
                ty,
                duration_ms=press_duration,
                device_id=device_id,
            )
            return await _post_action_cleanup(
                "long_press",
                {
                    "x": tx,
                    "y": ty,
                    "element_name": element_name,
                    "duration": press_duration,
                },
                ControllerResponse.success(
                    f"Long-pressed at ({tx}, {ty}) for {press_duration}ms"
                    + (f" (resolved from '{element_name}')" if element_name else "")
                ),
            )

        elif action == "swipe":
            if any(v is None for v in [x, y, x2, y2]):
                return ControllerResponse.error("Swipe requires x, y, x2, y2.")
            rx, ry = await _normalize_coordinates(x, y)
            rx2, ry2 = await _normalize_coordinates(x2, y2)
            await asyncio.to_thread(
                adb_driver.swipe,
                rx,
                ry,
                rx2,
                ry2,
                duration_ms=duration_ms,
                device_id=device_id,
            )
            return await _post_action_cleanup(
                "swipe",
                {"x1": rx, "y1": ry, "x2": rx2, "y2": ry2, "duration": duration_ms},
                ControllerResponse.swipe_result(
                    direction="custom", start=(rx, ry), end=(rx2, ry2)
                ),
            )

        elif action == "scroll":
            if not direction:
                return ControllerResponse.missing_param("direction")
            sw, sh = await asyncio.to_thread(
                adb_driver.get_screen_size, device_id=device_id
            )
            if isinstance(scroll_amount, (int, float)):
                scroll_ratio = min(1.0, max(0.1, float(scroll_amount)))
            else:
                amount_map = {"small": 0.3, "medium": 0.5, "large": 0.7, "full": 0.9}
                scroll_ratio = amount_map.get(scroll_amount, 0.5)

            scroll_distance = (
                int(sh * scroll_ratio)
                if direction in ("up", "down")
                else int(sw * scroll_ratio)
            )
            center_x = int(sw * 0.5)
            center_y = int(sh * 0.5)
            if element_name:
                resolved = await resolve_element(
                    element_name, element_role, timeout_val=timeout
                )
                if isinstance(resolved, str):
                    return resolved
                center_x, center_y = (
                    resolved.get("x", center_x),
                    resolved.get("y", center_y),
                )

            if direction == "up":
                start_x = end_x = center_x
                start_y, end_y = (
                    center_y - scroll_distance // 2,
                    center_y + scroll_distance // 2,
                )
            elif direction == "down":
                start_x = end_x = center_x
                start_y, end_y = (
                    center_y + scroll_distance // 2,
                    center_y - scroll_distance // 2,
                )
            elif direction == "left":
                start_y = end_y = center_y
                start_x, end_x = (
                    center_x - scroll_distance // 2,
                    center_x + scroll_distance // 2,
                )
            else:
                start_y = end_y = center_y
                start_x, end_x = (
                    center_x + scroll_distance // 2,
                    center_x - scroll_distance // 2,
                )

            start_x, start_y = max(0, min(sw, start_x)), max(0, min(sh, start_y))
            end_x, end_y = max(0, min(sw, end_x)), max(0, min(sh, end_y))

            await asyncio.to_thread(
                adb_driver.swipe,
                start_x,
                start_y,
                end_x,
                end_y,
                duration_ms=duration_ms,
                device_id=device_id,
            )
            return await _post_action_cleanup(
                "scroll",
                {
                    "direction": direction,
                    "amount": scroll_amount,
                    "element_name": element_name,
                },
                ControllerResponse.success(
                    f"Scrolled {direction} by {scroll_amount}"
                    + (f" (in '{element_name}')" if element_name else "")
                ),
            )

        elif action == "input_text":
            if not text:
                return ControllerResponse.missing_param("text")
            base_pkg = await _get_effective_package()
            if element_name:
                resolved = await resolve_element(
                    element_name,
                    element_role,
                    timeout_val=timeout,
                    expected_pkg=base_pkg,
                )
                if isinstance(resolved, str):
                    return resolved
                await asyncio.to_thread(
                    adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id
                )
            await asyncio.to_thread(adb_driver.input_text, text, device_id=device_id)
            return await _post_action_cleanup(
                "input_text",
                {"text": text, "element_name": element_name},
                ControllerResponse.input_result(
                    field_name=element_name, value=text[:50] if len(text) > 50 else text
                ),
            )

        elif action == "scroll_to_bottom":
            max_scrolls = int(kwargs.get("max_scrolls", 5))
            scroll_amt = kwargs.get("scroll_amount", "medium")

            size = await asyncio.to_thread(
                adb_driver.get_screen_size, device_id=device_id
            )
            width, height = size

            start_x = width // 2
            end_x = start_x

            if scroll_amt == "small":
                distance = height // 4
            elif scroll_amt == "large":
                distance = (height // 4) * 3
            else:
                distance = height // 2

            start_y = (height // 2) + (distance // 2)
            end_y = (height // 2) - (distance // 2)

            scroll_count = 0
            last_ui_hash = ""

            while scroll_count < max_scrolls:
                try:
                    curr_ui = await asyncio.to_thread(
                        adb_driver.dump_ui, device_id=device_id
                    )
                    curr_hash = str(hash(curr_ui))
                except Exception:
                    curr_hash = str(time.time())

                if curr_hash == last_ui_hash:
                    logger.info(
                        f"[Mobile] Scroll reached bottom (UI stable) after {scroll_count} scrolls."
                    )
                    break

                last_ui_hash = curr_hash

                await asyncio.to_thread(
                    adb_driver.swipe,
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    duration_ms=400,
                    device_id=device_id,
                )
                scroll_count += 1

            return ControllerResponse.success(
                "Scrolled to bottom.", note=f"Completed {scroll_count} iterations."
            )

        elif action == "press_key":
            if keycode is None:
                return ControllerResponse.missing_param("keycode")
            await asyncio.to_thread(adb_driver.press_key, keycode, device_id=device_id)
            return ControllerResponse.success(f"Pressed: {keycode}")

        return None
