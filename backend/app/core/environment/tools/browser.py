"""
Browser Control Tool — Agent-facing thin wrapper over BrowserController.

This module exposes `browser` as an @evoloop_tool so the Agent can
call it via function calling. All actual logic lives in:
  app.core.environment.controllers.browser.BrowserController
"""

import logging
from typing import Literal

from app.core.environment.controllers.browser import BrowserController
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    required_benefit="browser",
    summary_template="evoloop.tool_summary.browser",
    affected_path_keys=["url", "file_path"],
)
async def browser(
    action: Literal[
        # Navigation
        "navigate",
        "back",
        "forward",
        "reload",
        "get_url",
        "new_tab",
        "switch_tab",
        # Interaction
        "click",
        "double_click",
        "hover",
        "type_text",
        "select_option",
        "key_press",
        "scroll",
        "drag_drop",
        # Batch & File
        "batch",
        "upload",
        # Reading
        "get_text",
        "get_html",
        "get_attribute",
        "get_links",
        "find_element",
        # Perception
        "screenshot",
        "wait_for",
        "check_element",
        # Advanced
        "run_js",
        "get_cookies",
        "set_cookies",
        "local_storage",
        "network_wait",
        "dialog_handle",
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
    value: str
    | None = None,  # type_text content, select value/label, local_storage value
    key: str | None = None,  # key_press key
    source_selector: str | None = None,  # drag_drop source
    target_selector: str | None = None,  # drag_drop target
    direction: Literal["up", "down", "left", "right"] | None = None,
    amount: int = 300,  # scroll pixels
    clear_first: bool = True,  # for type_text: clear field before typing
    # Screenshot params
    full_page: bool = False,
    ocr: bool = False,  # run OCR on screenshot
    # Reading params
    attribute: str | None = None,  # get_attribute attr name
    # wait_for / check_element params
    state: Literal["visible", "hidden", "attached", "detached"] = "visible",
    url_pattern: str | None = None,  # wait_for URL match / network_wait URL pattern
    timeout_ms: int = 15_000,
    # Cookie / storage params
    cookies: list[dict] | None = None,
    storage_action: Literal["get", "set", "clear"] | None = None,
    storage_key: str | None = None,
    # Dialog params
    dialog_action: Literal["accept", "dismiss"] | None = None,
    dialog_text: str | None = None,  # text to type into a prompt dialog
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
    """通过 Playwright 控制一个持久化的 Chromium 浏览器（网页内 DOM 交互/内容提取/状态管理）。

    与 desktop（OS 级）互补。动作覆盖：导航（navigate/back/new_tab/switch_tab）、交互
    （click/type_text/select_option/key_press/scroll/drag_drop）、读取（get_text/get_html/
    get_attribute/get_links/find_element）、感知（screenshot[ocr=True 返回文本+坐标]/
    wait_for/check_element）、批量（actions 列表）与 upload、高级（run_js/cookies/
    local_storage/network_wait/dialog_handle）、生命周期（close）。

    纪律：等待用 wait_for 而非盲目 sleep；批量放已知稳定序列，页面状态未知时逐步验证；
    selector 优先于坐标。完整动作语义与流程加载 skill(name="Browser Automation SOP")。
    """
    return await BrowserController.execute(**locals())
