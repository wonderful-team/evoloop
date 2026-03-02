"""
Browser Control Tool — Playwright-based browser automation.

Provides the Agent with native browser-level control:
  - Full DOM access (click, type, extract text/HTML/links)
  - Navigation (URL, tabs, history, reload)
  - Visual perception (screenshot + immediate OCR)
  - Advanced capabilities (JS execution, cookies, network wait, dialogs)

`browser_control` is self-starting (will auto-launch Chrome if needed) and operates independently of OS-level tools for most web tasks.
"""
import asyncio
import logging
import os
import re
import tempfile
import time
from typing import Any, Literal

from app.core.config import settings
from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)



# ─────────────────────────────────────────────
#  Browser Manager (Persistent Singleton)
# ─────────────────────────────────────────────

class BrowserManager:
    """
    Manages a single, persistent Playwright browser session.

    Dual-mode architecture:
    ─────────────────────────────────────────────────────────
    Mode 1 (Takeover / CDP):  Detects an existing Chrome with `--remote-debugging-port`
                              and connects via ChromeDevTools Protocol. Agent actions
                              directly appear in the user's own browser window.

    Mode 2 (Auto-Launch / CDP): No existing Chrome found → launches a dedicated
                                Chrome instance (arch -arm64, separate profile dir)
                                with `--remote-debugging-port`, waits for it to boot,
                                then connects via CDP.

    Both modes use the same CDP connection path, so the rest of the codebase is
    completely unaware of which mode is active.

    Settings are managed in app.core.config.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: list = []
        self._active_page_idx: int = 0
        self._lock_pool = LoopBoundResource(asyncio.Lock)
        self._is_cdp = False
        self._chrome_proc = None  # Set if we auto-launched Chrome via subprocess

    async def get_page(self):
        """Return the active Page, lazily starting Chrome if needed."""
        async with self._lock_pool.get():
            if self._context is None:
                await self._start()
            ctx_pages = self._context.pages
            if not ctx_pages:
                self._pages = [await self._context.new_page()]
                self._active_page_idx = 0
            else:
                self._pages = list(ctx_pages)
                self._active_page_idx = min(self._active_page_idx, len(self._pages) - 1)
            return self._pages[self._active_page_idx]

    async def _start(self) -> None:
        import subprocess
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()

        # ─── Mode 1: Try Takeover (CDP – external Chrome already running) ──
        logger.info(f"[Browser] Attempting CDP takeover: {settings.CHROME_CDP_URL}")
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                settings.CHROME_CDP_URL, timeout=3000  # fast probe, 3 s
            )
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()
            logger.info("✅ [Browser] Mode 1: Took over existing Chrome via CDP.")
            self._is_cdp = True
        except Exception as e:
            logger.info(f"ℹ️ [Browser] No external Chrome found ({type(e).__name__}). Will auto-launch.")
            self._is_cdp = False

        # ─── Mode 2: Auto-Launch (subprocess → CDP) ─────────────────────────
        if not self._context:
            automation_dir = settings.CHROME_AUTOMATION_USER_DATA
            logger.info(f"[Browser] Mode 2: Launching Chrome-Automation → {automation_dir}")
            os.makedirs(automation_dir, exist_ok=True)

            import platform
            chrome_cmd = [settings.CHROME_EXECUTABLE]
            
            # Performance optimization: force native ARM64 on Apple Silicon Macs
            if platform.system() == "Darwin" and platform.machine() == "arm64":
                chrome_cmd = ["arch", "-arm64"] + chrome_cmd

            chrome_cmd.extend([
                f"--remote-debugging-port=9222",
                f"--user-data-dir={automation_dir}",
                "--disable-infobars",
                "--enable-extensions",
                "--no-first-run",
            ])
            try:
                self._chrome_proc = subprocess.Popen(
                    chrome_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info(f"[Browser] Chrome launched (pid={self._chrome_proc.pid}). Waiting {settings.CHROME_STARTUP_TIMEOUT}s...")
                await asyncio.sleep(settings.CHROME_STARTUP_TIMEOUT)

                self._browser = await self._playwright.chromium.connect_over_cdp(
                    settings.CHROME_CDP_URL, timeout=10000  # more lenient after launch
                )

                if self._browser.contexts:
                    self._context = self._browser.contexts[0]
                else:
                    self._context = await self._browser.new_context()
                self._is_cdp = True
                logger.info("✅ [Browser] Mode 2: auto-launched Chrome + CDP connected.")
            except Exception as e:
                logger.error(f"[Browser] Mode 2 (auto-launch CDP) failed: {e}")
                raise RuntimeError(
                    f"Browser startup failed. Could not connect to CDP at {settings.CHROME_CDP_URL}. "
                    "Please ensure Google Chrome is installed at the default path."
                ) from e

        # ─── Initialize page list ────────────────────────────────────────────
        if self._context.pages:
            self._pages = list(self._context.pages)
        else:
            self._pages = [await self._context.new_page()]
        self._active_page_idx = 0
        logger.info(f"[Browser] Ready — {len(self._pages)} page(s), mode={'CDP-Takeover' if self._is_cdp and not hasattr(self, '_chrome_proc') else 'CDP-AutoLaunch' if self._is_cdp else 'Launch'}.")

    async def new_tab(self, url: str | None = None):
        """Open a new tab, optionally navigate to url, and switch to it."""
        page = await self._context.new_page()
        self._pages = list(self._context.pages)
        self._active_page_idx = self._pages.index(page)
        if url:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        return page

    def switch_tab(self, index: int):
        """Switch active tab by index."""
        if index < 0 or index >= len(self._pages):
            raise IndexError(f"Tab index {index} out of range (0–{len(self._pages) - 1})")
        self._active_page_idx = index
        return self._pages[index]

    @property
    def tab_count(self) -> int:
        return len(self._pages)

    def get_status(self) -> dict:
        """Return connectivity and state info for environment prompts."""
        if not self._context:
            return {"mode": "Disconnected", "cdp_url": settings.CHROME_CDP_URL, "tab_count": 0}
        
        mode = "CDP-Takeover" if self._is_cdp and not self._chrome_proc else "CDP-AutoLaunch" if self._is_cdp else "Launch"
        active_url = "None"
        try:
            if self._pages and self._active_page_idx < len(self._pages):
                active_url = self._pages[self._active_page_idx].url
        except Exception:
            pass

        return {
            "mode": mode,
            "cdp_url": settings.CHROME_CDP_URL,
            "active_url": active_url,
            "tab_count": len(self._pages),
        }

    async def close(self) -> None:
        async with self._lock_pool.get():
            # 1. Close Playwright browser/context
            if self._is_cdp and self._browser:
                await self._browser.close()
            elif self._context:
                await self._context.close()
            
            if self._playwright:
                await self._playwright.stop()
            
            # 2. Terminate auto-launched subprocess if any
            if self._chrome_proc:
                logger.info(f"[Browser] Terminating auto-launched Chrome (pid={self._chrome_proc.pid})")
                try:
                    self._chrome_proc.terminate()
                    # Wait slightly for it to die
                    for _ in range(10):
                        if self._chrome_proc.poll() is not None:
                            break
                        await asyncio.sleep(0.1)
                    if self._chrome_proc.poll() is None:
                        self._chrome_proc.kill()
                except Exception as e:
                    logger.warning(f"[Browser] Failed to terminate Chrome subprocess: {e}")
                self._chrome_proc = None

            # 3. Reset state
            self._context = None
            self._browser = None
            self._playwright = None
            self._pages = []
            self._is_cdp = False
            self._active_page_idx = 0
        logger.info("[Browser] Browser closed.")


browser_manager = BrowserManager()


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _tmp_screenshot_path(
    purpose: str = "temp",
    bundle_id: str | None = None,
    suffix: str | None = None
) -> str:
    """Return a unique path for a browser screenshot using hierarchical storage."""
    try:
        from app.core.vision.storage import screenshot_storage
        return screenshot_storage.get_path(
            purpose=purpose,
            platform="browser",
            bundle_id=bundle_id,
            suffix=suffix
        )
    except Exception as e:
        logger.warning(f"[Browser] Failed to use hierarchical storage: {e}, using fallback")
        os.makedirs("/tmp/evoloop", exist_ok=True)
        return os.path.join("/tmp/evoloop", f"browser_{int(time.time() * 1000)}.png")


async def _run_ocr(filepath: str) -> str:
    """Run OCR on filepath and return formatted OCR lines (same as desktop_control)."""
    try:
        ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
        if ocr_result.success and ocr_result.elements:
            lines = [el.to_prompt_line() for el in ocr_result.elements]
            return "\n\n### OCR Results (Detected Text & Coordinates):\n" + "\n".join(lines)
        return "\n\n(OCR: no text detected)"
    except Exception as e:
        logger.error(f"[Browser] OCR failed: {e}")
        return f"\n\n(OCR Error: {e})"


def _resolve_selector(selector: str | None, text: str | None) -> str | None:
    """Prefer explicit selector; fall back to text-based locator."""
    if selector:
        return selector
    if text:
        # Playwright text selector shorthand
        return f"text={text}"
    return None


# ─────────────────────────────────────────────
#  Main Tool
# ─────────────────────────────────────────────

@evoloop_tool(is_pollable=True)
async def browser_control(
    action: Literal[
        # Navigation
        "navigate", "back", "forward", "reload", "get_url", "new_tab", "switch_tab",
        # Interaction
        "click", "double_click", "hover", "type_text", "select_option", "key_press",
        "scroll", "drag_drop",
        # Reading
        "get_text", "get_html", "get_attribute", "get_links", "find_element",
        # Perception
        "screenshot", "wait_for", "check_element",
        # Advanced
        "run_js", "get_cookies", "set_cookies", "local_storage",
        "network_wait", "dialog_handle",
        # Lifecycle
        "close",
    ],
    # Navigation params
    url: str | None = None,
    tab_index: int | None = None,
    # Locator params
    selector: str | None = None,
    text: str | None = None,
    # Interaction params
    value: str | None = None,          # type_text content, select value/label, local_storage value
    key: str | None = None,            # key_press key
    source_selector: str | None = None,  # drag_drop source
    target_selector: str | None = None,  # drag_drop target
    direction: Literal["up", "down", "left", "right"] | None = None,
    amount: int = 300,                 # scroll pixels
    clear_first: bool = True,          # for type_text: clear field before typing
    # Screenshot params
    full_page: bool = False,
    # Reading params
    attribute: str | None = None,      # get_attribute attr name
    # wait_for / check_element params
    state: Literal["visible", "hidden", "attached", "detached"] = "visible",
    url_pattern: str | None = None,    # wait_for URL match / network_wait URL pattern
    timeout_ms: int = 15_000,
    # Cookie / storage params
    cookies: list[dict] | None = None,
    storage_action: Literal["get", "set", "clear"] | None = None,
    storage_key: str | None = None,
    # Dialog params
    dialog_action: Literal["accept", "dismiss"] | None = None,
    dialog_text: str | None = None,    # text to type into a prompt dialog
    # JS execution
    script: str | None = None,
    # Advanced / batch flags
    x: int | None = None,
    y: int | None = None,
) -> str:
    """
    Control a persistent Chromium browser via Playwright.

    This tool provides browser-native automation that complements desktop_control
    (OS-level). Use browser_control when you need precise DOM interaction,
    content extraction, or browser state management inside a web page.

    ## Action Groups

    ### 🧭 Navigation
    - navigate: Go to `url`, waits for networkidle.
    - back / forward: Browser history.
    - reload: Refresh current page.
    - get_url: Return current URL + page title.
    - new_tab: Open a new tab (optionally at `url`); switches to it.
    - switch_tab: Switch active tab by `tab_index` (0-based).

    ### 🖱️ Interaction
    - click: Click `selector` or `text`. Falls back to (x, y) coordinates.
    - double_click: Double-click `selector` or `text`.
    - hover: Mouse-hover over `selector` (reveals tooltips / dropdowns).
    - type_text: Type `value` into `selector` / `text`; set `clear_first=False` to append.
    - select_option: Pick from a <select> by `value` or visible `text`.
    - key_press: Keyboard shortcut, e.g. "Enter", "Control+a", "Tab".
    - scroll: Scroll page or `selector` element by `amount` px in `direction`.
    - drag_drop: Drag `source_selector` and drop onto `target_selector`.

    ### 📖 Reading
    - get_text: Extract visible text from page or `selector`.
    - get_html: Get outerHTML of page or `selector`.
    - get_attribute: Get `attribute` value from `selector`.
    - get_links: Return all href links (optionally scoped to `selector`).
    - find_element: Check if `selector` / `text` exists, return position.

    ### 📷 Perception
    - screenshot: Capture page (`full_page=True` for full scroll). Immediately
      runs OCR and returns: image path + OCR text/coordinates (same format as
      desktop_control).
    - wait_for: Wait until `selector` / `text` / `url_pattern` matches `state`.
    - check_element: Return visible/checked/enabled status of `selector`.

    ### 🔧 Advanced
    - run_js: Execute `script` in page context. Returns JSON-serialisable result.
    - get_cookies: List all cookies for current domain.
    - set_cookies: Inject `cookies` list (for pre-authenticated sessions).
    - local_storage: Get / set / clear localStorage via `storage_action`.
    - network_wait: Wait for a network request matching `url_pattern` to complete.
    - dialog_handle: Accept or dismiss the next alert/confirm/prompt.

    ### ⚡ Lifecycle
    - close: Gracefully close the browser.

    Args:
        action: The operation to perform (see above).
        url: Target URL for navigate / new_tab.
        tab_index: Zero-based tab index for switch_tab (default: current).
        selector: CSS selector, XPath (prefix //), or Playwright locator string.
        text: Visible text to locate an element (alternative to selector).
        value: Text to type, select-option value/label, or localStorage value.
        key: Key or shortcut for key_press (e.g. "Enter", "Control+a").
        source_selector / target_selector: For drag_drop.
        direction: Scroll direction (up/down/left/right).
        amount: Scroll distance in pixels (default 300).
        clear_first: Whether to clear the field before typing (default True).
        full_page: Capture full scrollable page in screenshot.
        attribute: HTML attribute name for get_attribute.
        state: Element state to wait for in wait_for (default "visible").
        url_pattern: Substring/regex to match URL in wait_for / network_wait.
        timeout_ms: Max wait time in ms (default 15 000).
        cookies: List of cookie dicts for set_cookies.
        storage_action: get / set / clear for local_storage.
        storage_key: localStorage key for get/set.
        dialog_action: accept / dismiss for dialog_handle.
        dialog_text: Text to enter into a prompt dialog.
        script: JavaScript code string for run_js.
        x, y: Coordinates for click when no selector/text is available.
    """
    try:
        # ── Lifecycle ──────────────────────────────────────────────────────
        if action == "close":
            await browser_manager.close()
            return "✅ Browser closed."

        # ── Tab management without a page ─────────────────────────────────
        if action == "new_tab":
            page = await browser_manager.new_tab(url)
            count = browser_manager.tab_count
            return f"✅ New tab opened (tab {count - 1}/{count - 1}). URL: {page.url}"

        if action == "switch_tab":
            if tab_index is None:
                return "Error: 'tab_index' is required for switch_tab."
            page = browser_manager.switch_tab(tab_index)
            return f"✅ Switched to tab {tab_index}. URL: {page.url}"

        # ── All other actions need a live page ────────────────────────────
        page = await browser_manager.get_page()

        # ── Navigation ────────────────────────────────────────────────────
        if action == "navigate":
            if not url:
                return "Error: 'url' is required for navigate."
            await page.goto(url, wait_until="load", timeout=60_000)
            return f"✅ Navigated to: {page.url}\nTitle: {await page.title()}"

        elif action == "back":
            await page.go_back(wait_until="load", timeout=15_000)
            return f"✅ Navigated back. URL: {page.url}"

        elif action == "forward":
            await page.go_forward(wait_until="load", timeout=15_000)
            return f"✅ Navigated forward. URL: {page.url}"

        elif action == "reload":
            await page.reload(wait_until="load", timeout=20_000)
            return f"✅ Page reloaded. URL: {page.url}"

        elif action == "get_url":
            return f"URL: {page.url}\nTitle: {await page.title()}\nTabs open: {browser_manager.tab_count}"

        # ── Interaction ───────────────────────────────────────────────────
        elif action in ("click", "double_click"):
            loc = _resolve_selector(selector, text)
            if loc:
                target = page.locator(loc).first
                if action == "click":
                    await target.click(timeout=timeout_ms)
                else:
                    await target.dblclick(timeout=timeout_ms)
                verb = "Clicked" if action == "click" else "Double-clicked"
                return f"✅ {verb}: {loc}"
            elif x is not None and y is not None:
                if action == "click":
                    await page.mouse.click(x, y)
                else:
                    await page.mouse.dblclick(x, y)
                verb = "Clicked" if action == "click" else "Double-clicked"
                return f"✅ {verb} at ({x}, {y})."
            else:
                return "Error: Provide 'selector', 'text', or (x, y) for click/double_click."

        elif action == "hover":
            loc = _resolve_selector(selector, text)
            if not loc:
                return "Error: 'selector' or 'text' is required for hover."
            await page.locator(loc).first.hover(timeout=timeout_ms)
            return f"✅ Hovered over: {loc}"

        elif action == "type_text":
            loc = _resolve_selector(selector, text)
            if not loc:
                return "Error: 'selector' or 'text' is required for type_text."
            if value is None:
                return "Error: 'value' is required for type_text."
            target = page.locator(loc).first
            if clear_first:
                await target.clear(timeout=timeout_ms)
            await target.type(value, delay=30)
            preview = value[:60] + ("…" if len(value) > 60 else "")
            return f"✅ Typed into {loc}: '{preview}'"

        elif action == "select_option":
            loc = _resolve_selector(selector, text)
            if not loc:
                return "Error: 'selector' or 'text' is required for select_option."
            if value is None:
                return "Error: 'value' (option value or label) is required for select_option."
            # Try value first, then label
            try:
                await page.locator(loc).first.select_option(value=value, timeout=timeout_ms)
            except Exception:
                await page.locator(loc).first.select_option(label=value, timeout=timeout_ms)
            return f"✅ Selected option '{value}' in {loc}."

        elif action == "key_press":
            if not key:
                return "Error: 'key' is required for key_press."
            await page.keyboard.press(key)
            return f"✅ Key pressed: {key}"

        elif action == "scroll":
            if not direction:
                return "Error: 'direction' (up/down/left/right) is required for scroll."
            delta_x = {"left": -amount, "right": amount}.get(direction, 0)
            delta_y = {"up": -amount, "down": amount}.get(direction, 0)
            if selector:
                elem = page.locator(selector).first
                await elem.scroll_into_view_if_needed(timeout=timeout_ms)
                await elem.evaluate(f"el => el.scrollBy({delta_x}, {delta_y})")
            else:
                await page.mouse.wheel(delta_x, delta_y)
            return f"✅ Scrolled {direction} by {amount}px."

        elif action == "drag_drop":
            if not source_selector or not target_selector:
                return "Error: 'source_selector' and 'target_selector' are required for drag_drop."
            src = page.locator(source_selector).first
            tgt = page.locator(target_selector).first
            await src.drag_to(tgt, timeout=timeout_ms)
            return f"✅ Dragged '{source_selector}' → '{target_selector}'."

        # ── Reading ───────────────────────────────────────────────────────
        elif action == "get_text":
            if selector:
                content = await page.locator(selector).first.inner_text(timeout=timeout_ms)
            else:
                content = await page.inner_text("body")
            # Collapse excessive whitespace
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            max_len = 6000
            if len(content) > max_len:
                content = content[:max_len] + f"\n… [truncated, total {len(content)} chars]"
            return content

        elif action == "get_html":
            if selector:
                content = await page.locator(selector).first.outer_html()
            else:
                content = await page.content()
            max_len = 8000
            if len(content) > max_len:
                content = content[:max_len] + f"\n<!-- truncated, total {len(content)} chars -->"
            return content

        elif action == "get_attribute":
            if not selector:
                return "Error: 'selector' is required for get_attribute."
            if not attribute:
                return "Error: 'attribute' is required for get_attribute."
            val = await page.get_attribute(selector, attribute, timeout=timeout_ms)
            # If None, the attribute may be a DOM property (textContent, value, innerHTML…)
            # Fall back to JS property access
            if val is None:
                try:
                    val = await page.locator(selector).first.evaluate(f"el => el['{attribute}']")
                    if val is not None:
                        return f"Attribute (JS property) '{attribute}' of '{selector}': {str(val).strip()}"
                except Exception:
                    pass
            if val is None:
                return f"Attribute '{attribute}' of '{selector}': (not found)"
            return f"Attribute '{attribute}' of '{selector}': {val}"

        elif action == "get_links":
            scope = page.locator(selector) if selector else page
            # Collect all anchor hrefs
            links_raw = await scope.locator("a[href]").evaluate_all(
                "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
            )
            if not links_raw:
                return "(No links found)"
            lines = [f"[{i}] {lnk['text'][:60]} → {lnk['href']}" for i, lnk in enumerate(links_raw)]
            return f"Found {len(links_raw)} links:\n" + "\n".join(lines[:100])

        elif action == "find_element":
            loc = _resolve_selector(selector, text)
            if not loc:
                return "Error: 'selector' or 'text' is required for find_element."
            try:
                elem = page.locator(loc).first
                await elem.wait_for(state="attached", timeout=5_000)
                box = await elem.bounding_box()
                if box:
                    cx = int(box["x"] + box["width"] / 2)
                    cy = int(box["y"] + box["height"] / 2)
                    return f"✅ Element found: '{loc}' at ({cx}, {cy}), size {int(box['width'])}×{int(box['height'])}px."
                return f"✅ Element found: '{loc}' (not in viewport, no bounding box)."
            except Exception:
                return f"❌ Element not found: '{loc}'."

        # ── Perception ────────────────────────────────────────────────────
        elif action == "screenshot":
            filepath = _tmp_screenshot_path()
            try:
                if selector:
                    elem = page.locator(selector).first
                    await elem.screenshot(path=filepath, animations="disabled", timeout=timeout_ms)
                else:
                    await page.screenshot(path=filepath, full_page=full_page, animations="disabled", timeout=timeout_ms)
            except Exception as e:
                logger.error(f"[Browser] Screenshot action failed: {e}")
                return f"Error: Screenshot failed (timeout={timeout_ms}ms). Details: {e}"

            result_msg = f"Screenshot saved to: {filepath}"
            result_msg += await _run_ocr(filepath)
            return result_msg

        elif action == "wait_for":
            if url_pattern:
                # Wait for URL to match pattern
                import re as _re
                await page.wait_for_url(
                    _re.compile(url_pattern) if not url_pattern.startswith("http") else url_pattern,
                    timeout=timeout_ms,
                )
                return f"✅ URL matched pattern '{url_pattern}'. Current: {page.url}"
            loc = _resolve_selector(selector, text)
            if not loc:
                return "Error: Provide 'selector', 'text', or 'url_pattern' for wait_for."
            await page.locator(loc).first.wait_for(state=state, timeout=timeout_ms)
            return f"✅ Element '{loc}' reached state '{state}'."

        elif action == "check_element":
            if not selector:
                return "Error: 'selector' is required for check_element."
            elem = page.locator(selector).first
            try:
                visible = await elem.is_visible()
                enabled = await elem.is_enabled()
                checked = await elem.is_checked() if await elem.get_attribute("type") in ("checkbox", "radio") else None
            except Exception as e:
                return f"check_element error: {e}"
            parts = [f"visible={visible}", f"enabled={enabled}"]
            if checked is not None:
                parts.append(f"checked={checked}")
            return f"Element '{selector}': " + ", ".join(parts)

        # ── Advanced ──────────────────────────────────────────────────────
        elif action == "run_js":
            if not script:
                return "Error: 'script' is required for run_js."
            if selector:
                result = await page.locator(selector).first.evaluate(script)
            else:
                result = await page.evaluate(script)
            return f"JS result: {result}"

        elif action == "get_cookies":
            cookies_list = await page.context.cookies()
            lines = [f"[{i}] {c['name']}={c['value'][:40]} (domain: {c.get('domain','')})" for i, c in enumerate(cookies_list)]
            return f"Cookies ({len(cookies_list)}):\n" + "\n".join(lines) if lines else "(No cookies)"

        elif action == "set_cookies":
            if not cookies:
                return "Error: 'cookies' list is required for set_cookies."
            await page.context.add_cookies(cookies)
            return f"✅ {len(cookies)} cookie(s) set."

        elif action == "local_storage":
            if storage_action == "get":
                val_js = await page.evaluate(f"() => localStorage.getItem({repr(storage_key)})")
                return f"localStorage['{storage_key}'] = {val_js}"
            elif storage_action == "set":
                if storage_key is None or value is None:
                    return "Error: 'storage_key' and 'value' are required for local_storage set."
                await page.evaluate(f"() => localStorage.setItem({repr(storage_key)}, {repr(value)})")
                return f"✅ localStorage['{storage_key}'] set."
            elif storage_action == "clear":
                await page.evaluate("() => localStorage.clear()")
                return "✅ localStorage cleared."
            else:
                return "Error: 'storage_action' must be get / set / clear."

        elif action == "network_wait":
            if not url_pattern:
                return "Error: 'url_pattern' is required for network_wait."
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
            return f"✅ Network response captured:\nURL: {resp.url}\nStatus: {status}\nBody (preview): {body_preview}"

        elif action == "dialog_handle":
            if not dialog_action:
                return "Error: 'dialog_action' (accept/dismiss) is required for dialog_handle."

            async def _handler(dialog):
                if dialog_text and dialog.type == "prompt":
                    await dialog.accept(dialog_text)
                elif dialog_action == "accept":
                    await dialog.accept()
                else:
                    await dialog.dismiss()

            page.once("dialog", _handler)
            return f"✅ Dialog handler registered: will '{dialog_action}' next dialog."

        else:
            return f"Error: Unknown action '{action}'."

    except Exception as e:
        logger.error(f"[Browser] action='{action}' failed: {e}", exc_info=True)
        return f"Error: {e}"
