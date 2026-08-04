"""
Mobile Control Tool — Agent-facing thin wrapper over MobileController.

This module exposes `mobile_control` as an @evoloop_tool so the Agent can
call it via function calling. All actual logic lives in:
  app.core.environment.controllers.mobile.MobileController
"""

import logging
from typing import Literal

from app.core.environment.controllers.mobile import MobileController
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    required_benefit="mobile_control",
    summary_template="evoloop.tool_summary.mobile_control",
    affected_path_keys=["local_path", "remote_path"],
)
async def mobile_control(
    action: Literal["screenshot", "tap", "click", "long_press", "swipe", "scroll", "input_text", "press_key", "dump_ui", "list_devices", "get_info", "list_apps", "open_app", "push", "pull", "intent_flow", "read_sms", "gui_extract"] = "screenshot",
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
    Control an Android device via ADB with Local Reactive Loop (Reactor) support.

    This tool supports atomic actions and high-speed 'intent flows' for fluid interaction.

    Args:
        action: The action to perform:
            - "intent_flow": A sequence of intents (click/input) executed locally with high frequency.
            - "screenshot": Capture the device screen. Returns path to image file.
            - "tap": Tap at coordinates (x, y).
            - "click": Semantic click. Polls locally if element_name is used (Reactor).
            - "long_press": Long-press at (x, y) OR element_name.
            - "swipe": Swipe from (x, y) to (x2, y2).
            - "scroll": Semantic scroll in direction with amount (small/medium/large/full or custom float).
            - "input_text": Type text. If element_name given, taps it first.
            - "press_key": Press a key (home, back, enter, etc.).
            - "dump_ui": Get UI hierarchy as XML.
            - "list_devices": List connected devices.
            - "list_apps": List installed 3rd-party packages.
            - "open_app": Open app by package name (passed in 'text').
            - "push": Push a local file/directory to the device.
            - "pull": Pull a remote file/directory from the device.
            - "read_sms": Poll device SMS inbox with smart delays. 'text' = regex pattern. 'timeout' = max wait seconds (default 30). 'after_timestamp' = Unix timestamp (ms) to filter only new messages. Note: Waits 3s before first query, then polls every 2-5s.
            - "gui_extract": Intelligent text extraction from a region or near coordinates (x, y) using OCR.
        intents: List of intent dicts for "intent_flow" action.
                 E.g. [{"action": "click", "target": "Search"}, {"action": "input", "target": "SearchBox", "text": "iPhone"}]
                 For "input" action, if "target" or "element_name" is provided, will click the element first to focus.
        x, y, x2, y2: Coordinates (can be absolute or relative 0.0-1.0).
        element_name: Semantic name/label of the UI element.
        target: Alias for element_name (for cross-tool consistency).
        element_role: Optional role/class filter.
        text: Text to input OR package name.
        keycode: Key name or code for press_key.
        local_path: Full path on the host Mac (required for push/pull).
        remote_path: Full path on the Android device (required for push/pull).
        device_id: Optional device serial.
        ocr: Perform OCR on screenshot.
        scroll_amount: Amount to scroll - small (~30%), medium (~50%), large (~70%), full (~90%) of screen.
        after_timestamp: For "read_sms" action only. Unix timestamp in milliseconds. Only return SMS messages with date > this value. Use to filter out old messages and listen only for new ones sent after a specific point in time.
        region: Optional crop region for screenshots in "x,y,w,h" format (logical points). Used for targeted OCR or verification.
    """
    # Parameter alias: target -> element_name (cross-tool consistency)
    if target and not element_name:
        element_name = target
    return await MobileController.execute(**locals())
