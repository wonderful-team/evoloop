"""
Browser Controller — Core Playwright-based browser automation.

Extracted from app.domain.tools.environment.browser to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/browser.py thin wrapper).
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import Any

from app.core.context import ContextManager
from app.core.environment.controllers.utils import (
    BatchExecutor,
    RecordingContext,
    truncate_output,
)
from app.core.learning.trace_recorder import get_recorder
from app.core.vision import VisionTask, vision_engine
from app.infrastructure.drivers.browser import browser_manager
from app.utils import (
    ControllerResponse,
    PerceptionsFormatter,
    render_template,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────

def _tmp_screenshot_path(
    purpose: str = "temp",
    bundle_id: str | None = None,
    suffix: str | None = None
) -> str:
    """Return a unique path for a browser screenshot using hierarchical storage."""
    from app.core.vision.storage import screenshot_storage
    return screenshot_storage.get_path(
        purpose=purpose,
        platform="browser",
        bundle_id=bundle_id,
        suffix=suffix
    )


async def _run_ocr(filepath: str) -> str:
    """Run OCR on filepath and return formatted OCR lines."""
    try:
        # Browser contexts don't benefit from Atlas learning (dynamic web pages)
        ocr_result = await vision_engine.process(VisionTask.OCR, filepath, enable_atlas_learning=False)
        if ocr_result.success and ocr_result.elements:
            return "\n\n" + render_template(
                "core/vision/ocr_results.prompt.j2",
                platform="browser",
                elements=[el.model_dump() for el in ocr_result.elements],
                total_count=len(ocr_result.elements)
            )
        return "\n\n" + ControllerResponse.error("OCR: no text detected")
    except Exception as e:
        logger.error(f"[Browser] OCR failed: {e}")
        return "\n\n" + ControllerResponse.error("OCR Error.", details=str(e))


def _resolve_selector(selector: str | None, text: str | None) -> str | None:
    """Prefer explicit selector; fall back to text-based locator."""
    if selector:
        return selector
    if text:
        return f"text={text}"
    return None


# ─────────────────────────────────────────────
#  BrowserController
# ─────────────────────────────────────────────

class BrowserController:
    """
    Core browser automation logic via Playwright.

    All methods are classmethods (stateless) — browser state lives in
    the singleton `browser_manager` from infrastructure.
    """

    @classmethod
    async def execute(
        cls,
        action: str,
        url: str | None = None,
        tab_index: int | None = None,
        selector: str | None = None,
        text: str | None = None,
        value: str | None = None,
        key: str | None = None,
        source_selector: str | None = None,
        target_selector: str | None = None,
        direction: str | None = None,
        amount: int = 300,
        clear_first: bool = True,
        full_page: bool = False,
        ocr: bool = False,
        attribute: str | None = None,
        state: str = "visible",
        url_pattern: str | None = None,
        timeout_ms: int = 15_000,
        cookies: list[dict] | None = None,
        storage_action: str | None = None,
        storage_key: str | None = None,
        dialog_action: str | None = None,
        dialog_text: str | None = None,
        script: str | None = None,
        x: int | None = None,
        y: int | None = None,
        actions: list[dict] | None = None,
        continue_on_error: bool = True,
        delay_ms: int = 100,
        file_path: str | None = None,
        **kwargs: Any  # Accept extra arguments like 'purpose' for screenshots
    ) -> str:
        """Execute a browser action. All business logic lives here."""
        try:
            # ── Lifecycle ──────────────────────────────────────────────────────
            if action == "close":
                await browser_manager.close()
                return ControllerResponse.success("Browser closed.")

            # ── Tab management without a page ─────────────────────────────────
            if action == "new_tab":
                page = await browser_manager.new_tab(url)
                count = browser_manager.tab_count
                return ControllerResponse.success(f"New tab opened (tab {count - 1}/{count - 1}). URL: {page.url}")

            if action == "switch_tab":
                if tab_index is None:
                    return ControllerResponse.missing_param("tab_index")
                page = browser_manager.switch_tab(tab_index)
                return ControllerResponse.success(f"Switched to tab {tab_index}. URL: {page.url}")

            # ── All other actions need a live page ────────────────────────────
            page = await browser_manager.get_page()

            # Phase 5: Imitation Learning - Trace Recording
            thread_id = ContextManager.get_var("thread_id") or "default"
            recorder = get_recorder(thread_id)
            recording_ctx = RecordingContext(
                platform="web",
                recorder=recorder,
                screenshot_actions=("click", "type_text", "navigate", "submit")
            )

            async def _record(action_type: str, params: dict):
                async def screenshot_fn():
                    return await page.screenshot(animations="disabled")

                async def context_fn():
                    return {"url": page.url, "title": await page.title()}

                await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

            # --- Pre-action state capture for stasis detection ---
            pre_url = page.url
            try:
                pre_title = await page.title()
            except Exception:
                pre_title = ""

            # ── Navigation ────────────────────────────────────────────────────
            if action == "navigate":
                if not url:
                    return ControllerResponse.missing_param("url")
                await page.goto(url, wait_until="load", timeout=60_000)
                await _record("navigate", {"url": url})

                post_url = page.url
                post_title = await page.title()
                note = "The page URL and title remained unchanged after this action." if (post_url == pre_url and post_title == pre_title) else None
                return ControllerResponse.navigation_result(post_url, success=True, title=post_title)

            elif action == "back":
                await page.go_back(wait_until="load", timeout=15_000)
                await _record("back", {})
                return ControllerResponse.success(f"Navigated back. URL: {page.url}")

            elif action == "forward":
                await page.go_forward(wait_until="load", timeout=15_000)
                return ControllerResponse.success(f"Navigated forward. URL: {page.url}")

            elif action == "reload":
                await page.reload(wait_until="load", timeout=20_000)
                return ControllerResponse.success(f"Page reloaded. URL: {page.url}")

            elif action == "get_url":
                return ControllerResponse.success(
                    f"URL: {page.url}",
                    details=f"Title: {await page.title()}\nTabs open: {browser_manager.tab_count}"
                )

            # ── Interaction ───────────────────────────────────────────────────
            elif action in ("click", "double_click"):
                loc = _resolve_selector(selector, text)
                if loc:
                    # Prefer visible elements if multiple match
                    try:
                        # Wait up to 2s for a visible instance if there are multiple matches
                        visible_locator = page.locator(loc).filter(visible=True).first
                        if await visible_locator.count() > 0:
                             target = visible_locator
                        else:
                             # Wait for any visible one to appear
                             await page.locator(loc).first.wait_for(state="visible", timeout=3000)
                             target = page.locator(loc).filter(visible=True).first
                    except Exception as ve:
                        logger.debug(f"[Browser] Visibility wait failed: {ve}")
                        target = page.locator(loc).first

                    logger.debug(f"[Browser] Clicking locator: {loc} (target={target})")
                    if action == "click":
                        await target.click(timeout=timeout_ms)
                    else:
                        await target.dblclick(timeout=timeout_ms)
                    verb = "Clicked" if action == "click" else "Double-clicked"
                    await _record(action, {"selector": loc, "x": x, "y": y})

                    post_url = page.url
                    post_title = await page.title()
                    note = "The page URL and title remained unchanged after this click." if (post_url == pre_url and post_title == pre_title) else None
                    return ControllerResponse.action_result(
                        action=action, target=loc, success=True
                    )
                elif x is not None and y is not None:
                    if action == "click":
                        await page.mouse.click(x, y)
                    else:
                        await page.mouse.dblclick(x, y)
                    verb = "Clicked" if action == "click" else "Double-clicked"
                    await _record(action, {"x": x, "y": y})

                    post_url = page.url
                    post_title = await page.title()
                    note = "The page URL and title remained unchanged after this click." if (post_url == pre_url and post_title == pre_title) else None
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

                # Prefer visible elements
                target = page.locator(loc).first
                try:
                    # Wait up to 2s for a visible instance
                    visible_locator = page.locator(loc).filter(visible=True).first
                    if await visible_locator.count() > 0:
                        target = visible_locator
                    else:
                        await page.locator(loc).first.wait_for(state="visible", timeout=3000)
                        target = page.locator(loc).filter(visible=True).first
                except Exception as ve:
                    logger.debug(f"[Browser] Visibility wait failed for type_text: {ve}")
                    pass

                # --- Robustness: If target is not an input/textarea, look for one inside it ---
                try:
                    tag_name = await target.evaluate("node => node.tagName.toLowerCase()")
                    if tag_name not in ["input", "textarea"]:
                        logger.debug(f"[Browser] Target {tag_name} is not an input. Searching for child input...")
                        child_input = target.locator("input, textarea, [contenteditable='true']").first
                        if await child_input.count() > 0:
                            target = child_input
                            logger.debug(f"[Browser] Found child input: {target}")
                except Exception as ee:
                    logger.debug(f"[Browser] Failed to check/find child input: {ee}")

                logger.debug(f"[Browser] Typing into locator: {loc} (target={target})")
                # Log the value being typed (truncated for privacy/length)
                val_display = str(value)[:50] + ("..." if len(str(value)) > 50 else "")
                logger.info(f"[Browser] Typing value '{val_display}' into locator: {loc}")

                await target.fill(value, timeout=timeout_ms)
                await _record("type_text", {"selector": loc, "value": value})
                preview = value[:60] + ("…" if len(value) > 60 else "")
                return ControllerResponse.input_result(
                    field_name=loc,
                    value=preview
                )

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
                # Standardize Enter/Return for Playwright
                if key == "Return":
                    key = "Enter"
                await page.keyboard.press(key)
                await _record("key_press", {"key": key})
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
                await _record("scroll", {"direction": direction, "amount": amount, "selector": selector})
                return ControllerResponse.success(f"Scrolled {direction} by {amount}px.")

            elif action == "drag_drop":
                if not source_selector or not target_selector:
                    return ControllerResponse.error("'source_selector' and 'target_selector' are required for drag_drop.")
                src = page.locator(source_selector).first
                tgt = page.locator(target_selector).first
                await src.drag_to(tgt, timeout=timeout_ms)
                return ControllerResponse.success(f"Dragged '{source_selector}' → '{target_selector}'.")

            # ── Reading ───────────────────────────────────────────────────────
            elif action == "get_text":
                if selector:
                    content = await page.locator(selector).first.inner_text(timeout=timeout_ms)
                else:
                    content = await page.inner_text("body")
                content = re.sub(r"\n{3,}", "\n\n", content).strip()
                return truncate_output(content, max_len=20000, suffix="\n… [truncated, total {len(content)} chars]")

            elif action == "get_html":
                if selector:
                    content = await page.locator(selector).first.outer_html()
                else:
                    content = await page.content()
                return truncate_output(content, max_len=8000, suffix="\n<!-- truncated, total {len(content)} chars -->")

            elif action == "get_attribute":
                if not selector:
                    return ControllerResponse.missing_param("selector")
                if not attribute:
                    return ControllerResponse.missing_param("attribute")
                val = await page.get_attribute(selector, attribute, timeout=timeout_ms)
                if val is None:
                    try:
                        val = await page.locator(selector).first.evaluate(f"el => el['{attribute}']")
                        if val is not None:
                            return ControllerResponse.success(
                                f"Attribute (JS property) '{attribute}' of '{selector}'",
                                details=str(val).strip()
                            )
                    except Exception:
                        pass
                if val is None:
                    return ControllerResponse.not_found(attribute, item_type="attribute")
                return ControllerResponse.success(
                    f"Attribute '{attribute}' of '{selector}'",
                    details=str(val)
                )

            elif action == "get_links":
                scope = page.locator(selector) if selector else page
                links_raw = await scope.locator("a[href]").evaluate_all(
                    "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
                )
                return PerceptionsFormatter.links(links_raw)

            elif action == "find_element":
                loc = _resolve_selector(selector, text)
                if not loc:
                    return ControllerResponse.missing_param("selector or text")
                try:
                    elem = page.locator(loc).first
                    await elem.wait_for(state="attached", timeout=5_000)
                    box = await elem.bounding_box()
                    if box:
                        cx = int(box["x"] + box["width"] / 2)
                        cy = int(box["y"] + box["height"] / 2)
                        return ControllerResponse.success(
                            f"Element found: '{loc}' at ({cx}, {cy})",
                            details=f"Size: {int(box['width'])}×{int(box['height'])}px"
                        )
                    return ControllerResponse.success(
                        f"Element found: '{loc}'",
                        note="Not in viewport, no bounding box."
                    )
                except Exception:
                    return ControllerResponse.not_found(loc, item_type="element")

            elif action == "get_elements":
                loc = _resolve_selector(selector, text)
                if not loc:
                    return "[]"
                try:
                    elements = page.locator(loc)
                    count = await elements.count()
                    logger.info(f"[Browser] Found {count} elements for selector: {loc}")

                    # Optimization: Use batch JS evaluation instead of individual calls
                    # This reduces communication overhead from 2*N round-trips to 1
                    max_elements = min(count, 20)  # Limit to 20 for safety

                    js_batch_get_elements = """
                    (params) => {
                        const selector = params.selector;
                        const maxCount = params.maxCount;
                        const elements = document.querySelectorAll(selector);
                        const results = [];
                        for (let i = 0; i < Math.min(elements.length, maxCount); i++) {
                            const el = elements[i];
                            const rect = el.getBoundingClientRect();
                            results.push({
                                index: i,
                                selector: selector + ':nth-of-type(' + (i + 1) + ')',
                                text: el.innerText ? el.innerText.substring(0, 100) : '',
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            });
                        }
                        return results;
                    }
                    """

                    # Fallback to CSS selector if the locator is simple enough
                    # For complex Playwright selectors, we use the original method
                    if loc.startswith('[data-testid=') or loc.startswith('.') or loc.startswith('#') or ',' in loc:
                        # Try batch JS approach
                        try:
                            batch_results = await page.evaluate(js_batch_get_elements, {
                                "selector": loc,
                                "maxCount": max_elements
                            })
                            return json.dumps(batch_results)
                        except Exception as js_e:
                            logger.debug(f"[Browser] Batch JS failed, falling back: {js_e}")

                    # Fallback: Original serial approach for complex selectors
                    results = []
                    for i in range(max_elements):
                        el = elements.nth(i)
                        box = await el.bounding_box()
                        txt = await el.inner_text()
                        results.append({
                            "index": i,
                            "selector": f"{loc} >> nth={i}",
                            "text": txt[:100],
                            "x": box["x"] if box else 0,
                            "y": box["y"] if box else 0,
                            "width": box["width"] if box else 0,
                            "height": box["height"] if box else 0
                        })
                    return json.dumps(results)
                except Exception as e:
                    logger.error(f"[Browser] get_elements failed: {e}")
                    return "[]"

            # ── Perception ────────────────────────────────────────────────────
            elif action == "screenshot":
                filepath = _tmp_screenshot_path(purpose=kwargs.get("purpose", "temp"))
                try:
                    if selector:
                        elem = page.locator(selector).first
                        await elem.screenshot(path=filepath, animations="disabled", timeout=timeout_ms)
                    else:
                        await page.screenshot(path=filepath, full_page=full_page, animations="disabled", timeout=timeout_ms)
                except Exception as e:
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
                    import re as _re
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
                elem = page.locator(selector).first
                try:
                    visible = await elem.is_visible()
                    enabled = await elem.is_enabled()
                    checked = await elem.is_checked() if await elem.get_attribute("type") in ("checkbox", "radio") else None
                except Exception as e:
                    return ControllerResponse.error(f"check_element error: {e}")
                data = {"visible": visible, "enabled": enabled}
                if checked is not None:
                    data["checked"] = checked
                return ControllerResponse.success(
                    f"Element status information for: {selector}",
                    details=str(data)
                )

            # ── Advanced ──────────────────────────────────────────────────────
            elif action == "run_js":
                if not script:
                    return ControllerResponse.missing_param("script")
                if selector:
                    result = await page.locator(selector).first.evaluate(script)
                else:
                    result = await page.evaluate(script)
                return f"JS result: {result}"

            elif action == "get_cookies":
                cookies_list = await page.context.cookies()
                return PerceptionsFormatter.cookies(cookies_list)

            elif action == "set_cookies":
                if not cookies:
                    return ControllerResponse.missing_param("cookies")
                await page.context.add_cookies(cookies)
                return ControllerResponse.success(f"{len(cookies)} cookie(s) set.")

            elif action == "local_storage":
                if storage_action == "get":
                    val_js = await page.evaluate(f"() => localStorage.getItem({repr(storage_key)})")
                    return ControllerResponse.success(
                        f"localStorage['{storage_key}']",
                        details=str(val_js)
                    )
                elif storage_action == "set":
                    if storage_key is None or value is None:
                        return render_template("common/report/response.prompt.j2", success=False, message="'storage_key' and 'value' are required for local_storage set.")
                    await page.evaluate(f"() => localStorage.setItem({repr(storage_key)}, {repr(value)})")
                    return ControllerResponse.success(f"localStorage['{storage_key}'] set.")
                elif storage_action == "clear":
                    await page.evaluate("() => localStorage.clear()")
                    return ControllerResponse.success("localStorage cleared.")
                else:
                    return ControllerResponse.invalid_param("storage_action", "must be get / set / clear")

            elif action == "network_wait":
                if not url_pattern:
                    return ControllerResponse.missing_param("url_pattern")
                async with page.expect_response(
                    lambda r: url_pattern in r.url, timeout=timeout_ms
                ) as response_info:
                    pass
                resp = await response_info.value
                status = resp.status
                try:
                    body: Any = await resp.json()
                    body_preview = str(body)[:500]
                except Exception:
                    body_preview = (await resp.text())[:500]

                data = {
                    "URL": resp.url,
                    "Status": status,
                    "Body (preview)": body_preview
                }
                return ControllerResponse.success(
                    "Network response captured.",
                    details=str(data)
                )

            elif action == "wait_for_stability":
                # Wait until DOM stops changing or max timeout
                # Optimization: Use lightweight JS hash instead of full HTML content
                check_interval = 0.5
                max_checks = int(timeout_ms / 1000 / check_interval)
                last_hash = ""
                for _ in range(max_checks):
                    try:
                        # Use innerText length + element count + scrollHeight as lightweight stability hash
                        curr_hash = await page.evaluate(
                            "() => document.body.innerText.length + ':' + " +
                            "document.querySelectorAll('*').length + ':' + " +
                            "document.body.scrollHeight"
                        )
                        if curr_hash == last_hash:
                            return render_template("common/report/response.prompt.j2", success=True, message="Page stable (DOM hash matched).")
                        last_hash = curr_hash
                        await asyncio.sleep(check_interval)
                    except Exception:
                        break
                return ControllerResponse.success(
                    "Stability check finished.",
                    note="Page stability timeout reached."
                )

            elif action == "dialog_handle":
                if not dialog_action:
                    return ControllerResponse.missing_param("dialog_action")

                async def _handler(dialog):
                    if dialog_text and dialog.type == "prompt":
                        await dialog.accept(dialog_text)
                    elif dialog_action == "accept":
                        await dialog.accept()
                    else:
                        await dialog.dismiss()

                page.once("dialog", _handler)
                return ControllerResponse.success(f"Dialog handler registered: will '{dialog_action}' next dialog.")

            elif action == "scroll_to_bottom":
                # Get payload from kwargs (passed from macro engine)
                payload = kwargs.get("payload", {})
                max_scrolls = int(payload.get("max_scrolls", 5)) or 5
                delay_ms = int(payload.get("delay_ms", 2000)) or 2000
                item_selector = selector or "[class*='item'], [class*='card'], .feed-card"

                logger.info(f"[Browser] Starting scroll_to_bottom (max={max_scrolls}, delay={delay_ms}ms)")

                last_count = 0
                for i in range(max_scrolls):
                    # Get current count
                    try:
                        count = await page.locator(item_selector).count()
                    except:
                        count = 0

                    if count > last_count and last_count > 0:
                        logger.info(f"[Browser] Scroll {i}: Items increased {last_count} -> {count}")

                    last_count = count

                    # Scroll
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    await asyncio.sleep(delay_ms / 1000)

                    # Check if reached absolute bottom
                    is_bottom = await page.evaluate("(window.innerHeight + window.scrollY) >= document.body.scrollHeight - 100")
                    if is_bottom:
                        # Try one last small scroll to be sure
                        await page.evaluate("window.scrollBy(0, 500)")
                        await asyncio.sleep(1)
                        break

                final_count = await page.locator(item_selector).count()
                return ControllerResponse.success(f"Scrolled to bottom. Final items: {final_count}")

            elif action == "detect_pagination":
                # Returns a JSON string with pagination info
                js_detect = """
                (() => {
                    const nextPatterns = [
                        { text: /下一页/, weight: 10 },
                        { text: /更多/, weight: 6 },
                        { text: />/, weight: 5 },
                        { text: /Next/i, weight: 8 },
                        { selector: "a.next, .pagination-next, [aria-label*='Next'], [class*='next']", weight: 7 }
                    ];
                    
                    const matches = [];
                    const allElements = document.querySelectorAll('a, button, div[role="button"], span, li');
                    
                    allElements.forEach(el => {
                        const text = el.innerText || "";
                        let score = 0;
                        let patternUsed = "";
                        
                        for (const p of nextPatterns) {
                            if (p.text && p.text.test(text)) {
                                score += p.weight;
                                patternUsed = p.text.toString();
                            }
                            if (p.selector && el.matches(p.selector)) {
                                score += p.weight;
                                patternUsed = p.selector;
                            }
                        }
                        
                        if (score > 0 && el.offsetWidth > 0 && el.offsetHeight > 0) {
                            // Basic selector generation
                            let selector = el.tagName.toLowerCase();
                            if (el.id) selector += '#' + el.id;
                            if (el.className) selector += '.' + Array.from(el.classList).join('.');
                            
                            matches.push({
                                text: text.trim().substring(0, 30),
                                selector: selector,
                                score: score,
                                pattern: patternUsed
                            });
                        }
                    });
                    
                    // Also check for numeric sequences
                    const numbers = Array.from(document.querySelectorAll('a, button, li'))
                        .filter(el => /^[0-9]+$/.test(el.innerText.trim()) && el.offsetWidth > 0);
                    
                    return {
                        has_next: matches.length > 0,
                        next_selector: matches.length > 0 ? matches.sort((a, b) => b.score - a.score)[0].selector : null,
                        has_numbers: numbers.length > 2,
                        candidates: matches.sort((a, b) => b.score - a.score).slice(0, 3)
                    };
                })()
                """
                result = await page.evaluate(js_detect)
                return json.dumps(result)

            # ── Batch & File ──────────────────────────────────────────────────
            elif action == "batch":
                if not actions:
                    return ControllerResponse.missing_param("actions")

                batch_start = time.time()
                executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)

                async def _exec_action(action_dict: dict) -> str:
                    params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
                    return await cls.execute(action=action_dict.get("action", "unknown"), **params)

                await executor.execute(actions, _exec_action)
                return executor.format_summary(time.time() - batch_start)

            elif action == "upload":
                if not file_path:
                    return ControllerResponse.missing_param("file_path")
                if not os.path.isfile(file_path):
                    return ControllerResponse.not_found(file_path, item_type="file")
                loc = _resolve_selector(selector, text)
                if not loc:
                    return ControllerResponse.missing_param("selector or text")
                try:
                    await page.locator(loc).first.set_input_files(file_path)
                    return ControllerResponse.success(f"Uploaded file '{os.path.basename(file_path)}' to {loc}")
                except Exception as e:
                    logger.error(f"[Browser] Upload failed: {e}")
                    return ControllerResponse.error("Upload failed.", details=str(e))

            else:
                return ControllerResponse.error(f"Unknown action '{action}'.")

        except Exception as e:
            error_msg = f"[Browser] action='{action}' failed: {e}"
            if continue_on_error:
                logger.warning(f"Optional {error_msg}. Continuing.")
                return ControllerResponse.success("Optional action failed, continuing.", details=str(e))
            logger.error(error_msg, exc_info=True)
            return ControllerResponse.error(f"Action failed: {action}", details=str(e))
