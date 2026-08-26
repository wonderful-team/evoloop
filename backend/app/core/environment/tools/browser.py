"""
Browser Control Tool — Agent-facing thin wrapper over BrowserController.

This module exposes `browser_control` as an @evoloop_tool so the Agent can
call it via function calling. All actual logic lives in:
  app.core.environment.controllers.browser.BrowserController
"""

import logging
from typing import Literal

from app.core.environment.controllers.browser import BrowserController
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    required_benefit="browser_control",
    summary_template="evoloop.tool_summary.browser_control",
    affected_path_keys=["url", "file_path"],
)
async def browser_control(
    action: Literal[
        # Navigation
        "navigate", "back", "forward", "reload", "get_url", "new_tab", "switch_tab",
        # Interaction
        "click", "double_click", "hover", "type_text", "select_option", "key_press",
        "scroll", "drag_drop",
        # Batch & File
        "batch", "upload",
        # Reading
        "get_text", "get_html", "get_attribute", "get_links", "find_element",
        # Perception
        "screenshot", "wait_for", "check_element",
        # Advanced
        "run_js", "get_cookies", "set_cookies", "local_storage",
        "network_wait", "dialog_handle",
        # Lifecycle
        "close",
    ] = "navigate",
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
    ocr: bool = False,                  # run OCR on screenshot
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
    # Batch params
    actions: list[dict] | None = None,
    continue_on_error: bool = True,
    delay_ms: int = 100,
    # Upload params
    file_path: str | None = None,
) -> str:
    """
    Control a persistent Chromium browser via Playwright.

    This tool provides browser-native automation that complements desktop_control
    (OS-level). Use browser_control when you need precise DOM interaction,
    content extraction, or browser state management inside a web page.

    Action Groups:

    NAVIGATION:
    - navigate: Go to `url`, waits for networkidle.
    - back / forward: Browser history.
    - reload: Refresh current page.
    - get_url: Return current URL + page title.
    - new_tab: Open a new tab (optionally at `url`); switches to it.
    - switch_tab: Switch active tab by `tab_index` (0-based).

    INTERACTION:
    - click: Click `selector` or `text`. Falls back to (x, y) coordinates.
    - double_click: Double-click `selector` or `text`.
    - hover: Mouse-hover over `selector` (reveals tooltips / dropdowns).
    - type_text: Type `value` into `selector` / `text`; set `clear_first=False` to append.
    - select_option: Pick from a <select> by `value` or visible `text`.
    - key_press: Keyboard shortcut, e.g. "Enter", "Control+a", "Tab".
    - scroll: Scroll page or `selector` element by `amount` px in `direction`.
    - drag_drop: Drag `source_selector` and drop onto `target_selector`.

    READING:
    - get_text: Extract visible text from page or `selector`.
    - get_html: Get outerHTML of page or `selector`.
    - get_attribute: Get `attribute` value from `selector`.
    - get_links: Return all href links (optionally scoped to `selector`).
    - find_element: Check if `selector` / `text` exists, return position.

    PERCEPTION:
    - screenshot: Capture page (`full_page=True` for full scroll). Immediately
      runs OCR and returns: image path + OCR text/coordinates (same format as
      desktop_control).
    - wait_for: Wait until `selector` / `text` / `url_pattern` matches `state`.
    - check_element: Return visible/checked/enabled status of `selector`.

    BATCH & FILE OPERATIONS:
    - batch: Execute multiple actions in sequence. Provide `actions` list.
    - upload: Upload a file to a file input element. Provide `file_path`.

    ADVANCED:
    - run_js: Execute `script` in page context. Returns JSON-serialisable result.
    - get_cookies: List all cookies for current domain.
    - set_cookies: Inject `cookies` list (for pre-authenticated sessions).
    - local_storage: Get / set / clear localStorage via `storage_action`.
    - network_wait: Wait for a network request matching `url_pattern` to complete.
    - dialog_handle: Accept or dismiss the next alert/confirm/prompt.

    LIFECYCLE:
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
        ocr: Run OCR on screenshot and return detected text (default False).
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
        actions: List of action dicts for batch mode.
        continue_on_error: For batch mode, whether to continue on error (default True).
        delay_ms: For batch mode, delay between actions in ms (default 100).
        file_path: Full path to local file for upload action.
    """
    return await BrowserController.execute(**locals())
