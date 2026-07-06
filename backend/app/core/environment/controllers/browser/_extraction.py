"""
Browser controller mixin — extraction/reading actions (get_text, get_html, etc.).
"""
import json
import logging
import re

from app.core.environment.controllers.utils import truncate_output
from app.utils.controller_response import ControllerResponse, PerceptionsFormatter

from ._utils import _resolve_selector

logger = logging.getLogger(__name__)


class BrowserExtractionMixin:

    @classmethod
    async def _handle_extraction(cls, action: str, **ctx) -> str | None:
        page = ctx["page"]
        selector = ctx.get("selector")
        text = ctx.get("text")
        attribute = ctx.get("attribute")
        timeout_ms = ctx.get("timeout_ms", 15_000)

        if action == "get_text":
            if selector:
                content = await page.locator(selector).first.inner_text(timeout=timeout_ms)
            else:
                content = await page.inner_text("body")
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            return truncate_output(content, max_len=20000, suffix="\n\u2026 [truncated, total {len(content)} chars]")

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
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)
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
                        details=f"Size: {int(box['width'])}\u00d7{int(box['height'])}px"
                    )
                return ControllerResponse.success(
                    f"Element found: '{loc}'",
                    note="Not in viewport, no bounding box."
                )
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                return ControllerResponse.not_found(loc, item_type="element")

        elif action == "get_elements":
            loc = _resolve_selector(selector, text)
            if not loc:
                return "[]"
            try:
                elements = page.locator(loc)
                count = await elements.count()
                logger.info(f"[Browser] Found {count} elements for selector: {loc}")

                max_elements = min(count, 20)

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

                if loc.startswith('[data-testid=') or loc.startswith('.') or loc.startswith('#') or ',' in loc:
                    try:
                        batch_results = await page.evaluate(js_batch_get_elements, {
                            "selector": loc,
                            "maxCount": max_elements
                        })
                        return json.dumps(batch_results)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as js_e:
                        logger.debug(f"[Browser] Batch JS failed, falling back: {js_e}")

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
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[Browser] get_elements failed: {e}")
                return "[]"

        return None
