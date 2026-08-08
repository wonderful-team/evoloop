"""
Desktop controller mixin — interaction actions (click, type, scroll, drag_drop).
"""

import asyncio
import logging

from app.core.environment.controllers.desktop._shortcuts import get_shortcut
from app.infrastructure.drivers.macos import macos_driver
from app.utils.controller_response import ControllerResponse
from app.utils.geometry import normalize_coordinates

logger = logging.getLogger(__name__)


class DesktopInteractionMixin:
    @classmethod
    async def _handle_interaction(cls, action: str, **ctx) -> str | None:
        recording_func = ctx["recording_func"]
        get_cached_app_info = ctx["get_cached_app_info"]
        x = ctx.get("x")
        y = ctx.get("y")
        x2 = ctx.get("x2")
        y2 = ctx.get("y2")
        element_name = ctx.get("element_name")
        element_role = ctx.get("element_role")
        text = ctx.get("text")
        key = ctx.get("key")
        direction = ctx.get("direction")
        amount = ctx.get("amount", 300)
        force_keystroke = ctx.get("force_keystroke", False)
        source_element = ctx.get("source_element")
        target_element = ctx.get("target_element")
        duration_ms = ctx.get("duration_ms", 500)

        if action in ("click", "double_click"):
            if element_name and action == "click":
                try:
                    app_info = await get_cached_app_info()
                    bundle_id = app_info.get("bundle_id", "")
                    if shortcut := get_shortcut(bundle_id, element_name):
                        logger.info(f"[Desktop] Converting click('{element_name}') to shortcut '{shortcut}'")
                        await asyncio.to_thread(macos_driver.key_press, shortcut)
                        await recording_func("key_press", {"key": shortcut, "converted_from_click": element_name})
                        return f"Pressed shortcut '{shortcut}' (converted from click on '{element_name}') - Faster!"
                except Exception as e:
                    logger.debug(f"[Desktop] Shortcut conversion failed: {e}, falling back to click")

            target_x, target_y = x, y
            element_path = None

            if element_name:
                logger.info(f"[Desktop] Attempting to resolve semantic target: {element_name}")
                resolved = await cls._resolve_element(element_name, element_role)
                if isinstance(resolved, str):
                    return resolved

                if resolved.get("source") == "atlas_strategy":
                    strategy_type = resolved.get("strategy")
                    params = resolved.get("parameters", {})
                    if strategy_type == "search_then_click":
                        return ControllerResponse.error(
                            f"'{element_name}' is in a dynamic app. Strategy required.",
                            details=f"Use search approach: {params.get('description', 'Search for the element')}. Direct coordinates are unreliable.",
                        )
                    elif strategy_type == "static_click" and params.get("resource_id"):
                        element_path = params.get("resource_id")

                if resolved.get("type") == "path":
                    element_path = resolved.get("value")
                target_x = resolved.get("x", target_x)
                target_y = resolved.get("y", target_y)

            if element_path:
                res = await asyncio.to_thread(macos_driver.perform_ax_action, element_path, "AXPress")
                if "Error" not in res:
                    return ControllerResponse.success(f"Natively clicked '{element_name}' without moving the mouse.")
                logger.warning(f"[Desktop] Native AX action failed: {res}. Falling back to physical click.")

            if target_x is None or target_y is None:
                return ControllerResponse.error(f"'x' and 'y' coordinates OR 'element_name' are required for {action} action.")

            screen_w, screen_h = await asyncio.to_thread(macos_driver.get_screen_size)
            target_x, target_y = normalize_coordinates(target_x, target_y, screen_w, screen_h)
            if not (0 <= target_x <= screen_w and 0 <= target_y <= screen_h):
                return ControllerResponse.error(f"Coordinates ({target_x}, {target_y}) are out of screen bounds ({screen_w}x{screen_h}).")

            if action == "click":
                await asyncio.to_thread(macos_driver.click, target_x, target_y)
                await recording_func("click", {"x": target_x, "y": target_y, "element_name": element_name})
                return ControllerResponse.tap_result(target_x, target_y, element_name=element_name, success=True)
            else:
                await asyncio.to_thread(macos_driver.double_click, target_x, target_y)
                await recording_func("double_click", {"x": target_x, "y": target_y, "element_name": element_name})
                return ControllerResponse.success(
                    f"Visually double-clicked at ({target_x}, {target_y})"
                    + (f" (resolved from '{element_name}')" if element_name else ".")
                )

        elif action == "type_text":
            if not text:
                return ControllerResponse.missing_param("text")
            await asyncio.to_thread(macos_driver.type_text, text, force_keystroke=force_keystroke)
            await recording_func("type_text", {"text": text, "force_keystroke": force_keystroke})
            return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''} (via {'keystroke' if force_keystroke else 'clipboard'})"

        elif action == "key_press":
            if not key:
                return ControllerResponse.missing_param("key")
            if key.lower().startswith("key") and len(key) == 4:
                key = key[3:].lower()
            await asyncio.to_thread(macos_driver.key_press, key)
            await recording_func("key_press", {"key": key})
            return ControllerResponse.success(f"Pressed key: {key}")

        elif action == "scroll":
            if not direction:
                return ControllerResponse.missing_param("direction")
            try:
                from Quartz import (
                    CGEventCreateScrollWheelEvent,
                    CGEventPost,
                    kCGHIDEventTap,
                )

                if direction == "up":
                    delta_y, delta_x = amount, 0
                elif direction == "down":
                    delta_y, delta_x = -amount, 0
                elif direction == "left":
                    delta_x, delta_y = -amount, 0
                else:
                    delta_x, delta_y = amount, 0
                event = CGEventCreateScrollWheelEvent(None, 0, 2, delta_y, delta_x)
                CGEventPost(kCGHIDEventTap, event)
                await recording_func("scroll", {"direction": direction, "amount": amount})
                return ControllerResponse.success(f"Scrolled {direction} by {amount}px.")
            except ImportError:
                key_map = {
                    "up": "pageup",
                    "down": "pagedown",
                    "left": "left",
                    "right": "right",
                }
                k = key_map.get(direction)
                if k:
                    presses = max(1, amount // 300)
                    for _ in range(presses):
                        await asyncio.to_thread(macos_driver.key_press, k)
                        await asyncio.sleep(0.1)
                    await recording_func("scroll", {"direction": direction, "amount": amount, "method": "key"})
                    return ControllerResponse.success(f"Scrolled {direction} (~{amount}px) via key_press.")
                return ControllerResponse.error(f"Unable to scroll {direction}.")

        elif action == "drag_drop":
            source_x, source_y = x, y
            target_x, target_y = x2, y2
            if source_element:
                resolved = await cls._resolve_element(source_element)
                if isinstance(resolved, str):
                    return resolved
                if "x" in resolved:
                    source_x, source_y = resolved["x"], resolved["y"]
                else:
                    return ControllerResponse.not_found(source_element, item_type="source element")
            if target_element:
                resolved = await cls._resolve_element(target_element)
                if isinstance(resolved, str):
                    return resolved
                if "x" in resolved:
                    target_x, target_y = resolved["x"], resolved["y"]
                else:
                    return ControllerResponse.not_found(target_element, item_type="target element")
            if source_x is None or source_y is None or target_x is None or target_y is None:
                return ControllerResponse.error("Drag-drop requires source and target coordinates, or element names.")
            screen_w, screen_h = await asyncio.to_thread(macos_driver.get_screen_size)
            source_x, source_y = normalize_coordinates(source_x, source_y, screen_w, screen_h)
            target_x, target_y = normalize_coordinates(target_x, target_y, screen_w, screen_h)
            try:
                from Quartz import (
                    CGEventCreateMouseEvent,
                    CGEventPost,
                    CGPointMake,
                    kCGEventLeftMouseDown,
                    kCGEventLeftMouseDragged,
                    kCGEventLeftMouseUp,
                    kCGHIDEventTap,
                )

                source_point = CGPointMake(source_x, source_y)
                target_point = CGPointMake(target_x, target_y)
                CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, source_point, 0))
                await asyncio.sleep(0.05)
                steps = max(5, duration_ms // 50)
                for i in range(steps):
                    point = CGPointMake(
                        source_x + (target_x - source_x) * (i + 1) / steps,
                        source_y + (target_y - source_y) * (i + 1) / steps,
                    )
                    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, point, 0))
                    await asyncio.sleep(duration_ms / 1000 / steps)
                CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, target_point, 0))
                return ControllerResponse.success(
                    f"Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y}) in {duration_ms}ms."
                )
            except ImportError:
                return ControllerResponse.error("Drag-drop requires Quartz/pyobjc components.")

        return None
