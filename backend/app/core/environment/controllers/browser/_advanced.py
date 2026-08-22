"""
Browser controller mixin — advanced actions (run_js, cookies, localStorage, etc.).
"""

import asyncio
import json
import logging

from app.core.vision.perceptions_formatter import PerceptionsFormatter
from app.utils.controller_response import ControllerResponse
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class BrowserAdvancedMixin:
    @classmethod
    async def _handle_advanced(cls, action: str, **ctx) -> str | None:
        page = ctx["page"]
        selector = ctx.get("selector")
        script = ctx.get("script")
        cookies = ctx.get("cookies")
        storage_action = ctx.get("storage_action")
        storage_key = ctx.get("storage_key")
        value = ctx.get("value")
        url_pattern = ctx.get("url_pattern")
        timeout_ms = ctx.get("timeout_ms", 15_000)
        kwargs = ctx.get("kwargs", {})
        frame_selector = kwargs.get("frame_selector")
        frame_wait_for_selector = kwargs.get("frame_wait_for_selector")
        dialog_action = ctx.get("dialog_action")
        dialog_text = ctx.get("dialog_text")
        kwargs = ctx.get("kwargs", {})

        if action == "run_js":
            if not script:
                return ControllerResponse.missing_param("script")
            if frame_selector:
                target_frame = None
                deadline = asyncio.get_event_loop().time() + timeout_ms / 1000.0
                while target_frame is None and asyncio.get_event_loop().time() < deadline:
                    for frame in page.frames:
                        furl = frame.url or ""
                        if frame_selector in furl:
                            target_frame = frame
                            break
                        if frame_wait_for_selector:
                            try:
                                if await frame.evaluate(
                                    f"() => !!document.querySelector({frame_wait_for_selector!r})"
                                ):
                                    target_frame = frame
                                    break
                            except Exception:
                                pass
                    if target_frame is None:
                        await asyncio.sleep(0.3)
                if target_frame is None:
                    logger.warning(
                        f"[Browser] frame_selector '{frame_selector}' no match. frames={[f.url[:60] for f in page.frames]}"
                    )
                    return ControllerResponse.error(
                        f"No iframe matched frame_selector '{frame_selector}'"
                    )
                if frame_wait_for_selector:
                    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000.0
                    while asyncio.get_event_loop().time() < deadline:
                        try:
                            found = await target_frame.evaluate(
                                f"() => !!document.querySelector({frame_wait_for_selector!r})"
                            )
                            if found:
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(0.3)
                try:
                    result = await target_frame.evaluate(script)
                except Exception as e:
                    logger.exception("[Browser] run_js failed in frame: %s", e)
                    return ControllerResponse.error("run_js failed", details=str(e))
            elif selector:
                try:
                    result = await page.locator(selector).first.evaluate(script)
                except Exception as e:
                    logger.exception("[Browser] run_js failed on element: %s", e)
                    return ControllerResponse.error("run_js failed", details=str(e))
            else:
                for attempt in range(2):
                    try:
                        result = await page.evaluate(script)
                        break
                    except Exception as e:
                        msg = str(e)
                        if "Execution context was destroyed" in msg and attempt == 0:
                            logger.warning("[Browser] run_js hit stale execution context, retrying...")
                            await asyncio.sleep(1.0)
                            continue
                        logger.exception("[Browser] run_js failed: %s", e)
                        return ControllerResponse.error("run_js failed", details=str(e))
                else:
                    result = None
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
                return ControllerResponse.success(f"localStorage['{storage_key}']", details=str(val_js))
            elif storage_action == "set":
                if storage_key is None or value is None:
                    return render_template(
                        "common/report/response.prompt.j2",
                        success=False,
                        message="'storage_key' and 'value' are required for local_storage set.",
                    )
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
            from typing import Any

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

            data = {"URL": resp.url, "Status": status, "Body (preview)": body_preview}
            return ControllerResponse.success("Network response captured.", details=str(data))

        elif action == "wait_for_stability":
            check_interval = 0.5
            max_checks = int(timeout_ms / 1000 / check_interval)
            last_hash = ""
            for _ in range(max_checks):
                try:
                    curr_hash = await page.evaluate(
                        "() => document.body.innerText.length + ':' + "
                        "document.querySelectorAll('*').length + ':' + "
                        "document.body.scrollHeight"
                    )
                    if curr_hash == last_hash:
                        return render_template(
                            "common/report/response.prompt.j2",
                            success=True,
                            message="Page stable (DOM hash matched).",
                        )
                    last_hash = curr_hash
                    await asyncio.sleep(check_interval)
                except Exception:
                    break
            return ControllerResponse.success("Stability check finished.", note="Page stability timeout reached.")

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
            payload = kwargs.get("payload", {})
            max_scrolls = int(payload.get("max_scrolls", 5)) or 5
            delay_ms_val = int(payload.get("delay_ms", 2000)) or 2000
            item_selector = selector or "[class*='item'], [class*='card'], .feed-card"

            logger.info(f"[Browser] Starting scroll_to_bottom (max={max_scrolls}, delay={delay_ms_val}ms)")

            last_count = 0
            for i in range(max_scrolls):
                try:
                    count = await page.locator(item_selector).count()
                except Exception:
                    count = 0

                if count > last_count and last_count > 0:
                    logger.info(f"[Browser] Scroll {i}: Items increased {last_count} -> {count}")

                last_count = count

                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                await asyncio.sleep(delay_ms_val / 1000)

                is_bottom = await page.evaluate("(window.innerHeight + window.scrollY) >= document.body.scrollHeight - 100")
                if is_bottom:
                    await page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(1)
                    break

            final_count = await page.locator(item_selector).count()
            return ControllerResponse.success(f"Scrolled to bottom. Final items: {final_count}")

        elif action == "detect_pagination":
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

        return None
