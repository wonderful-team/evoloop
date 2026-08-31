"""
Mobile Control Tool — Agent-facing thin wrapper over MobileController.

This module exposes `mobile` as an @evoloop_tool so the Agent can
call it via function calling. All actual logic lives in:
  app.core.environment.controllers.mobile.MobileController
"""

import logging
from typing import Literal

from app.core.environment.controllers.mobile import MobileController
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    required_benefit="mobile",
    summary_template="evoloop.tool_summary.mobile",
    affected_path_keys=["local_path", "remote_path"],
)
async def mobile(
    action: Literal[
        "screenshot",
        "tap",
        "click",
        "long_press",
        "swipe",
        "scroll",
        "input_text",
        "press_key",
        "dump_ui",
        "list_devices",
        "get_info",
        "list_apps",
        "open_app",
        "push",
        "pull",
        "intent_flow",
        "read_sms",
        "gui_extract",
    ] = "screenshot",
    x: int | None = None,
    y: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    element_name: str | None = None,
    target: str | None = None,  # Alias for element_name (cross-tool consistency)
    element_role: str | None = None,
    text: str | None = None,
    keycode: int | str | None = None,
    device_id: str | None = None,
    local_path: str | None = None,
    remote_path: str | None = None,
    duration_ms: int = 300,
    wait_after_ms: int = 0,
    ocr: bool = False,
    timeout: float = 8.0,
    intents: list[dict] | None = None,
    # Scroll params
    direction: Literal["up", "down", "left", "right"] | None = None,
    scroll_amount: Literal["small", "medium", "large", "full"] = "medium",
    # SMS specific params
    after_timestamp: int | None = None,
    # Vision params
    region: str | None = None,
) -> str:
    """
    通过 ADB + 本地响应式循环（Reactor）控制 Android 设备。

    这是探索/操作已连接安卓手机的**专用工具**：用 "dump_ui" 读界面树、
    tap/输入/滑动/滚动、截图、打开 App。**始终优先用本工具，不要用 bash 跑裸 adb 命令**：
    - "dump_ui" 走 uiautomator2，能绕过很多 App 对 native `adb shell uiautomator dump`
      的屏蔽（native 可能失败或抓到错误的 App）。
    - 截图/tap/滚动都经过设备抽象，正确处理 device_id。

    Args:
        action: 要执行的动作：
            - "intent_flow": 本地高频执行的一系列 intent（click/input）。
            - "screenshot": 截取设备屏幕。返回图片文件路径。
            - "tap": 在坐标 (x, y) 点按。
            - "click": 语义点击。给 element_name 时用 Reactor 本地轮询。
            - "long_press": 在 (x, y) 或 element_name 长按。
            - "swipe": 从 (x, y) 滑到 (x2, y2)。
            - "scroll": 按方向与幅度语义滚动（small/medium/large/full 或自定义浮点）。
            - "input_text": 输入文本。给 element_name 时会先点它。
            - "press_key": 按键（home、back、enter 等）。
            - "dump_ui": 获取 UI 层级 XML。
            - "list_devices": 列出已连接设备。
            - "list_apps": 列出已安装的第三方包。
            - "open_app": 按包名打开 App（传 'text'）。
            - "push": 推送本地文件/目录到设备。
            - "pull": 从设备拉取远程文件/目录。
            - "read_sms": 带智能延迟轮询设备短信。'text'=正则，'timeout'=最大等待秒数
              （默认 30），'after_timestamp'=Unix 毫秒时间戳，只过滤更新的消息。
              注意：首次查询前等 3s，然后每 2-5s 轮询。
            - "gui_extract": 用 OCR 从区域或坐标 (x, y) 附近智能提取文本。
        intents: "intent_flow" 动作的 intent dict 列表。
                 如 [{"action": "click", "target": "Search"}, {"action": "input", "target": "SearchBox", "text": "iPhone"}]
                 对 "input" 动作，提供 "target" 或 "element_name" 时会先点该元素聚焦。
        x, y, x2, y2: 坐标（可以是绝对或相对 0.0-1.0）。
        element_name: UI 元素的语义名/标签。
        target: element_name 的别名（跨工具一致性）。
        element_role: 可选角色/类过滤。
        text: 要输入的文本 或 包名。
        keycode: press_key 的键名或键码。
        local_path: 宿主机 Mac 上的完整路径（push/pull 需要）。
        remote_path: Android 设备上的完整路径（push/pull 需要）。
        device_id: 可选设备序列号。
        ocr: 是否对截图做 OCR。
        scroll_amount: 滚动幅度 - small(~30%) / medium(~50%) / large(~70%) / full(~90%)。
        after_timestamp: 仅 "read_sms" 用。Unix 毫秒时间戳，只返回晚于此时间的短信。
                         用于过滤旧消息、只监听某时间点之后的新消息。
        region: 截图可选裁剪区域 "x,y,w,h" 格式（逻辑点）。用于定向 OCR 或验证。
    """
    # Parameter alias: target -> element_name (cross-tool consistency)
    if target and not element_name:
        element_name = target
    return await MobileController.execute(**locals())
