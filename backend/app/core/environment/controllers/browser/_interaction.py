"""
Browser controller mixin — interaction actions (click, type, scroll, etc.).
"""

import logging

from app.utils.controller_response import ControllerResponse

from ._utils import _resolve_selector

logger = logging.getLogger(__name__)


class BrowserInteractionMixin:
    @classmethod
    async def _handle_interaction(cls, action: str, **ctx) -> str | None:
        page = ctx["page"]
        recording_func = ctx["recording_func"]
        selector = ctx.get("selector")
        text = ctx.get("text")
        value = ctx.get("value")
        key = ctx.get("key")
        source_selector = ctx.get("source_selector")
        target_selector = ctx.get("target_selector")
        direction = ctx.get("direction")
        amount = ctx.get("amount", 300)
        clear_first = ctx.get("clear_first", True)
        x = ctx.get("x")
        y = ctx.get("y")
        timeout_ms = ctx.get("timeout_ms", 15_000)

        if action in ("click", "double_click"):
            loc = _resolve_selector(selector, text)
            if loc:
                try:
                    visible_locator = page.locator(loc).filter(visible=True).first
                    if await visible_locator.count() > 0:
                        target = visible_locator
                    else:
                        await page.locator(loc).first.wait_for(state="visible", timeout=3000)
                        target = page.locator(loc).filter(visible=True).first
                except Exception as ve:
                    logger.debug(f"[Browser] Visibility wait failed: {ve}", exc_info=True)
                    target = page.locator(loc).first

                logger.debug(f"[Browser] Clicking locator: {loc} (target={target})")
                if action == "click":
                    await target.click(timeout=timeout_ms)
                else:
                    await target.dblclick(timeout=timeout_ms)
                await recording_func(action, {"selector": loc, "x": x, "y": y})

                return ControllerResponse.action_result(
                    action=action, target=loc, success=True
                )
            elif x is not None and y is not None:
                if action == "click":
                    await page.mouse.click(x, y)
                else:
                    await page.mouse.dblclick(x, y)
                await recording_func(action, {"x": x, "y": y})

                return ControllerResponse.tap_result(x, y, success=True)
            else:
                return ControllerResponse.error("Provide 'selector', 'text', or (x, y) for click/double_click.")

        elif action == "hover":
            loc = _resolve_selector(selector, text)
            if not loc:
                return ControllerResponse.missing_param("selector or text")
            await page.locator(loc).first.hover(timeout=timeout_ms)
            return ControllerResponse.success(f"Hovered over: {loc}")

        elif action == "type_text":
            loc = _resolve_selector(selector, text)
            if not loc:
                return ControllerResponse.missing_param("selector or text")
            if value is None:
                return ControllerResponse.missing_param("value")

            target = page.locator(loc).first
            try:
                visible_locator = page.locator(loc).filter(visible=True).first
                if await visible_locator.count() > 0:
                    target = visible_locator
                else:
                    await page.locator(loc).first.wait_for(state="visible", timeout=3000)
                    target = page.locator(loc).filter(visible=True).first
            except Exception as ve:
                logger.debug(f"[Browser] Visibility wait failed for type_text: {ve}", exc_info=True)

            try:
                tag_name = await target.evaluate("node => node.tagName.toLowerCase()")
                if tag_name not in ["input", "textarea"]:
                    logger.debug(f"[Browser] Target {tag_name} is not an input. Searching for child input...")
                    child_input = target.locator("input, textarea, [contenteditable='true']").first
                    if await child_input.count() > 0:
                        target = child_input
                        logger.debug(f"[Browser] Found child input: {target}")
            except Exception as ee:
                logger.debug(f"[Browser] Failed to check/find child input: {ee}", exc_info=True)

            logger.debug(f"[Browser] Typing into locator: {loc} (target={target})")
            val_display = str(value)[:50] + ("..." if len(str(value)) > 50 else "")
            logger.info(f"[Browser] Typing value '{val_display}' into locator: {loc} (clear_first={clear_first})")

            if clear_first:
                await target.fill(value, timeout=timeout_ms)
            else:
                await target.press_sequentially(value, timeout=timeout_ms)
            await recording_func("type_text", {"selector": loc, "value": value, "clear_first": clear_first})
            preview = value[:60] + ("\u2026" if len(value) > 60 else "")
            return ControllerResponse.input_result(field_name=loc, value=preview)

        elif action == "select_option":
            loc = _resolve_selector(selector, text)
            if not loc:
                return ControllerResponse.missing_param("selector or text")
            if value is None:
                return ControllerResponse.missing_param("value")
            try:
                await page.locator(loc).first.select_option(value=value, timeout=timeout_ms)
            except Exception:
                await page.locator(loc).first.select_option(label=value, timeout=timeout_ms)
            return ControllerResponse.success(f"Selected option '{value}' in {loc}.")

        elif action == "key_press":
            if not key:
                return ControllerResponse.missing_param("key")
            if key == "Return":
                key = "Enter"
            await page.keyboard.press(key)
            await recording_func("key_press", {"key": key})
            return ControllerResponse.success(f"Key pressed: {key}")

        elif action == "scroll":
            if not direction:
                return ControllerResponse.missing_param("direction")
            delta_x = {"left": -amount, "right": amount}.get(direction, 0)
            delta_y = {"up": -amount, "down": amount}.get(direction, 0)
            if selector:
                elem = page.locator(selector).first
                await elem.scroll_into_view_if_needed(timeout=timeout_ms)
                await elem.evaluate(f"el => el.scrollBy({delta_x}, {delta_y})")
            else:
                await page.mouse.wheel(delta_x, delta_y)
            await recording_func("scroll", {"direction": direction, "amount": amount, "selector": selector})
            return ControllerResponse.success(f"Scrolled {direction} by {amount}px.")

        elif action == "drag_drop":
            if not source_selector or not target_selector:
                return ControllerResponse.error("'source_selector' and 'target_selector' are required for drag_drop.")
            src = page.locator(source_selector).first
            tgt = page.locator(target_selector).first
            await src.drag_to(tgt, timeout=timeout_ms)
            return ControllerResponse.success(f"Dragged '{source_selector}' \u2192 '{target_selector}'.")

        return None
