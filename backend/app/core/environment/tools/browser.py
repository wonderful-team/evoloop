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
    """
    通过 Playwright 控制一个持久化的 Chromium 浏览器。

    本工具提供浏览器原生自动化，与 desktop（OS 级）互补。需要在网页内做精确的 DOM
    交互、内容提取或浏览器状态管理时用 browser。

    动作分组：

    导航（NAVIGATION）：
    - navigate: 跳转到 `url`，等待 networkidle。
    - back / forward: 浏览器历史。
    - reload: 刷新当前页。
    - get_url: 返回当前 URL + 页面标题。
    - new_tab: 打开新标签页（可选带 `url`）；并切换到它。
    - switch_tab: 按 `tab_index`（从 0 开始）切换活动标签页。

    交互（INTERACTION）：
    - click: 点击 `selector` 或 `text`。可回退到 (x, y) 坐标。
    - double_click: 双击 `selector` 或 `text`。
    - hover: 鼠标悬停在 `selector` 上（显示 tooltip/下拉）。
    - type_text: 向 `selector` / `text` 输入 `value`；设 `clear_first=False` 可追加。
    - select_option: 按 `value` 或可见 `text` 从 <select> 选择。
    - key_press: 键盘快捷键，如 "Enter"、"Control+a"、"Tab"。
    - scroll: 按 `amount` 像素沿 `direction` 滚动页面或 `selector` 元素。
    - drag_drop: 拖动 `source_selector` 并放到 `target_selector`。

    读取（READING）：
    - get_text: 从页面或 `selector` 提取可见文本。
    - get_html: 获取页面或 `selector` 的 outerHTML。
    - get_attribute: 从 `selector` 获取 `attribute` 属性值。
    - get_links: 返回所有 href 链接（可选限定在 `selector` 内）。
    - find_element: 检查 `selector` / `text` 是否存在，返回位置。

    感知（PERCEPTION）：
    - screenshot: 截取页面（`full_page=True` 截整页滚动）。立即跑 OCR 并返回：
      图片路径 + OCR 文本/坐标（与 desktop 同格式）。
    - wait_for: 等待 `selector` / `text` / `url_pattern` 满足 `state`。
    - check_element: 返回 `selector` 的可见/勾选/启用状态。

    批量与文件（BATCH & FILE OPERATIONS）：
    - batch: 按顺序执行多个动作。提供 `actions` 列表。
    - upload: 上传文件到文件输入元素。提供 `file_path`。

    高级（ADVANCED）：
    - run_js: 在页面上下文执行 `script`。返回 JSON 可序列化结果。
    - get_cookies: 列出当前域的所有 cookie。
    - set_cookies: 注入 `cookies` 列表（用于预登录会话）。
    - local_storage: 通过 `storage_action` get/set/clear localStorage。
    - network_wait: 等待匹配 `url_pattern` 的网络请求完成。
    - dialog_handle: 接受或关闭下一个 alert/confirm/prompt。

    生命周期（LIFECYCLE）：
    - close: 优雅关闭浏览器。

    Args:
        action: 要执行的操作（见上）。
        url: navigate / new_tab 的目标 URL。
        tab_index: switch_tab 的标签页索引（从 0 开始，默认当前）。
        selector: CSS 选择器、XPath（// 前缀）或 Playwright locator 字符串。
        text: 定位元素的可见文本（selector 的替代）。
        value: 要输入的文本、select-option 的 value/label，或 localStorage 值。
        key: key_press 的键或快捷键（如 "Enter"、"Control+a"）。
        source_selector / target_selector: drag_drop 用。
        direction: 滚动方向（up/down/left/right）。
        amount: 滚动距离像素（默认 300）。
        clear_first: 输入前是否清空字段（默认 True）。
        full_page: 截图是否截取整页可滚动内容。
        ocr: 是否对截图跑 OCR 并返回检测文本（默认 False）。
        attribute: get_attribute 的 HTML 属性名。
        state: wait_for 等待的元素状态（默认 "visible"）。
        url_pattern: wait_for / network_wait 匹配 URL 的子串/正则。
        timeout_ms: 最大等待毫秒（默认 15 000）。
        cookies: set_cookies 的 cookie dict 列表。
        storage_action: local_storage 的 get / set / clear。
        storage_key: get/set 的 localStorage 键。
        dialog_action: dialog_handle 的 accept / dismiss。
        dialog_text: 向 prompt 对话框输入的文本。
        script: run_js 的 JavaScript 代码字符串。
        x, y: 无 selector/text 时 click 用的坐标。
        actions: batch 模式的动作 dict 列表。
        continue_on_error: batch 模式是否出错继续（默认 True）。
        delay_ms: batch 模式动作间延迟毫秒（默认 100）。
        file_path: upload 动作的本地文件完整路径。
    """
    return await BrowserController.execute(**locals())
