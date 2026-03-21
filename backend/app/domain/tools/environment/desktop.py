"""
Desktop Control Tool — Agent-facing thin wrapper over DesktopController.

This module exposes `desktop_control`, `verify_ui_state`, `quick_check_screen`
as @evoloop_tools so the Agent can call them via function calling.
All actual logic lives in:
  app.core.environment.controllers.desktop_controller.DesktopController
"""
from typing import Literal
from app.core.tools import evoloop_tool
from app.core.environment.controllers.desktop_controller import DesktopController

import logging
logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "桌面控制", "en": "Desktop Control"}
)
async def desktop_control(
    action: Literal["screenshot", "click", "double_click", "type_text", "key_press", "open_app", "applescript", "get_info", "list_apps", "batch", "get_active_app", "scroll", "drag_drop", "dump_ui", "gui_extract"],
    x: int | None = None,
    y: int | None = None,
    element_name: str | None = None,
    target: str | None = None,  # Alias for element_name (cross-tool consistency)
    element_role: str | None = None,
    text: str | None = None,
    key: str | None = None,
    app_name: str | None = None,
    script: str | None = None,
    region: str | None = None,
    force_keystroke: bool = False,
    ocr: bool = False,
    actions: list[dict] | None = None,
    continue_on_error: bool = True,
    delay_ms: int = 300,
    # Scroll params
    direction: Literal["up", "down", "left", "right"] | None = None,
    amount: int = 300,
    # Drag drop params
    x2: int | None = None,
    y2: int | None = None,
    source_element: str | None = None,
    target_element: str | None = None,
    duration_ms: int = 500,
    # Dump UI params
    role_filter: str | None = None,
    name_filter: str | None = None,
    max_depth: int = 10,
) -> str:
    """
    Control the MacOS desktop - screenshot, click, type, and more.

    This tool enables direct interaction with the Mac desktop environment.
    Use in combination with analyze_image for vision-guided automation.

    Args:
        action: The action to perform:
            - "screenshot": Capture the screen. Returns the path to the image file.
            - "click": Click at coordinates (x, y) OR by element_name.
            - "double_click": Double-click at coordinates (x, y) OR by element_name.
            - "type_text": Type the given text string.
            - "key_press": Press a special key (enter, escape, tab, etc.).
            - "open_app": Open or focus an application by name.
            - "applescript": Execute raw AppleScript code. WARNING: Do NOT use this for dynamic apps (WeChat, Chrome, Electron apps) as they lack robust AppleScript support. Use native type_text/click instead.
            - "get_info": Get system hardware and OS environment info.
            - "list_apps": List installed applications in /Applications.
            - "get_active_app": Get the currently focused application's name, title, and window bounds.
            - "scroll": Scroll in the given direction by amount pixels.
            - "drag_drop": Drag from source to target (by element name or coordinates).
            - "dump_ui": Dump the Accessibility Tree as JSON array of UI elements.
            - "gui_extract": Intelligent text extraction from a region or near coordinates (x, y) using OCR.
        x: X coordinate for click action.
        y: Y coordinate for click action.
        element_name: Semantic name/label of the UI element to click (e.g., "Login", "Close").
        target: Alias for element_name (for cross-tool consistency).
        element_role: Optional role filter for the element (e.g., "AXButton", "AXTextField").
        text: Text to type for type_text action.
        key: Key name or combination for key_press action (e.g., "enter", "tab", "a", "command+a", "shift+tab").
        app_name: Application name for open_app action (e.g., "Safari", "Terminal").
        script: AppleScript code for applescript action.
        region: Optional region "x,y,w,h" for screenshot action.
        force_keystroke: If True for type_text, uses slow AppleScript keystroke instead of fast clipboard paste.
        ocr: If True for "screenshot", immediately performs OCR and returns text elements + coordinates.
        actions: List of action dicts for batch mode. Each dict has "action" and matching params.
        continue_on_error: For batch mode, whether to continue on error (default True).
        delay_ms: For batch mode, delay between actions in ms (default 100).
        direction: Scroll direction (up/down/left/right) for scroll action.
        amount: Scroll amount in pixels (default 300).
        x2, y2: Target coordinates for drag_drop action.
        source_element: Source element name for drag_drop (alternative to x, y).
        target_element: Target element name for drag_drop (alternative to x2, y2).
        duration_ms: Duration of drag operation in milliseconds (default 500).
        role_filter: For dump_ui, filter elements by role (e.g., 'AXButton').
        name_filter: For dump_ui, filter elements by name (partial match).
        max_depth: For dump_ui, maximum depth to traverse (default 10).
    """
    return await DesktopController.execute(
        action=action, x=x, y=y, element_name=element_name, target=target,
        element_role=element_role, text=text, key=key, app_name=app_name,
        script=script, region=region, force_keystroke=force_keystroke, ocr=ocr,
        actions=actions, continue_on_error=continue_on_error, delay_ms=delay_ms,
        direction=direction, amount=amount, x2=x2, y2=y2,
        source_element=source_element, target_element=target_element,
        duration_ms=duration_ms, role_filter=role_filter, name_filter=name_filter,
        max_depth=max_depth,
    )


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "验证UI状态", "en": "Verify UI State"}
)
async def verify_ui_state(
    expected_element: str | None = None,
    expected_role: str | None = None,
    expected_text: str | None = None,
    timeout_seconds: int = 5,
) -> str:
    """
    Verify if a specific UI element or text is present on the screen using AX Tree.
    Use this after 'click' or 'type_text' to ensure the UI responded as expected.

    Args:
        expected_element: Partial name of the UI element to look for.
        expected_role: Optional role of the element (e.g., 'AXWindow', 'AXButton').
        expected_text: Optional text that should be present anywhere in the tree.
        timeout_seconds: (Not currently implemented for polling, but performs one immediate check).
    """
    return await DesktopController.verify_ui_state(
        expected_element=expected_element, expected_role=expected_role,
        expected_text=expected_text, timeout_seconds=timeout_seconds,
    )


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "快速检查屏幕", "en": "Quick Check Screen"}
)
async def quick_check_screen(
    check_type: Literal["has_text", "has_element", "is_loaded"],
    target: str | None = None,
    timeout_seconds: int = 5,
) -> str:
    """
    Fast screen state check using AX Tree (no LLM, ~500ms vs ~12s for analyze_image).

    Use this instead of analyze_image for simple checks like:
    - "Is the page loaded?" -> quick_check_screen("is_loaded")
    - "Does it show 'AI news'?" -> quick_check_screen("has_text", "AI news")
    - "Is there a Search button?" -> quick_check_screen("has_element", "Search")

    Args:
        check_type: What to check for:
            - "has_text": Check if target text appears anywhere on screen
            - "has_element": Check if an element with target name exists
            - "is_loaded": Check if UI has stabilized (elements present, no loading indicators)
        target: The text or element name to search for (for has_text/has_element)
        timeout_seconds: Polling timeout (checks every 500ms until timeout)

    Returns:
        Quick check result (much faster than analyze_image)
    """
    return await DesktopController.quick_check_screen(
        check_type=check_type, target=target, timeout_seconds=timeout_seconds,
    )
