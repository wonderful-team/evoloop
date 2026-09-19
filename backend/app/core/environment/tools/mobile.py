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
    """通过 ADB + 本地响应式循环（Reactor）控制 Android 设备。

    这是探索/操作已连接安卓手机的**专用工具**（截图/tap/输入/滚动/dump_ui 读界面树/
    open_app/intent_flow 批量/read_sms 听验证码/push-pull 文件）。

    **始终优先用本工具，不要用 bash 跑裸 adb 命令**：dump_ui 走 uiautomator2，能绕过
    很多 App 对 native `adb shell uiautomator dump` 的屏蔽（native 可能失败或抓到错误
    的 App）；截图/tap/滚动经设备抽象，正确处理 device_id。

    坐标可为绝对像素或相对 0.0-1.0；给 element_name/target 时 click/input 走 Reactor
    本地轮询。完整动作语义、intent_flow 格式、read_sms 轮询节奏等加载
    skill(name="Mobile Device SOP")。
    """
    # Parameter alias: target -> element_name (cross-tool consistency)
    if target and not element_name:
        element_name = target
    return await MobileController.execute(**locals())
