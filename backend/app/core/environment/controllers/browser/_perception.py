"""
Browser controller mixin — perception actions (screenshot, wait_for, check_element).
"""
import logging
import re as _re

from app.utils.controller_response import ControllerResponse

from ._utils import _resolve_selector, _run_ocr, _tmp_screenshot_path

logger = logging.getLogger(__name__)


class BrowserPerceptionMixin:

    @classmethod
    async def _handle_perception(cls, action: str, **ctx) -> str | None:
        page = ctx["page"]
        selector = ctx.get("selector")
        text = ctx.get("text")
        full_page = ctx.get("full_page", False)
        ocr = ctx.get("ocr", False)
        state = ctx.get("state", "visible")
        url_pattern = ctx.get("url_pattern")
        timeout_ms = ctx.get("timeout_ms", 15_000)
        kwargs = ctx.get("kwargs", {})

        if action == "screenshot":
            filepath = _tmp_screenshot_path(purpose=kwargs.get("purpose", "temp"))
            try:
                if selector:
                    elem = page.locator(selector).first
                    await elem.screenshot(path=filepath, animations="disabled", timeout=timeout_ms)
                else:
                    await page.screenshot(path=filepath, full_page=full_page, animations="disabled", timeout=timeout_ms)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                logger.error(f"[Browser] Screenshot action failed: {e}")
                return ControllerResponse.error(
                    f"Screenshot failed (timeout={timeout_ms}ms).",
                    details=str(e)
                )

            result_msg = ControllerResponse.screenshot_result(success=True, filename=filepath)
            if ocr:
                result_msg += await _run_ocr(filepath)
            return result_msg

        elif action == "wait_for":
            if url_pattern:
                await page.wait_for_url(
                    _re.compile(url_pattern) if not url_pattern.startswith("http") else url_pattern,
                    timeout=timeout_ms,
                )
                return ControllerResponse.success(
                    f"URL matched pattern '{url_pattern}'.",
                    details=f"Current: {page.url}"
                )
            loc = _resolve_selector(selector, text)
            if not loc:
                return ControllerResponse.error("Provide 'selector', 'text', or 'url_pattern' for wait_for.")
            await page.locator(loc).first.wait_for(state=state, timeout=timeout_ms)
            return ControllerResponse.success(f"Element '{loc}' reached state '{state}'.")

        elif action == "check_element":
            if not selector:
                return ControllerResponse.missing_param("selector")
            if await page.locator(selector).count() == 0:
                return ControllerResponse.success(
                    f"Not found: {selector}",
                    details="visible=False, enabled=False"
                )
            elem = page.locator(selector).first
            try:
                visible = await elem.is_visible()
                enabled = await elem.is_enabled()
                checked = await elem.is_checked() if await elem.get_attribute("type") in ("checkbox", "radio") else None
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                return ControllerResponse.error(f"check_element error: {e}")
            parts = [f"visible={visible}", f"enabled={enabled}"]
            if checked is not None:
                parts.append(f"checked={checked}")
            return ControllerResponse.success(
                f"Found element: {selector}",
                details=", ".join(parts)
            )

        return None
