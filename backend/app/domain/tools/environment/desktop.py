"""
Desktop Control Tool — Agent-facing thin wrapper over DesktopController.

This module exposes `desktop_control`, `verify_ui_state`, `quick_check_screen`
as @evoloop_tools so the Agent can call them via function calling.
All actual logic lives in:
  app.core.environment.controllers.desktop_controller.DesktopController
"""
import logging
from typing import Literal

from app.core.environment.controllers.desktop_controller import DesktopController
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class DesktopControlRequest(DynamicBaseModel):
    """Structured request for desktop automation actions."""

    action: Literal["screenshot", "click", "double_click", "type_text", "key_press", "open_app", "applescript", "get_info", "list_apps", "batch", "get_active_app", "scroll", "drag_drop", "dump_ui", "gui_extract"] = "screenshot"
    x: int | None = None
    y: int | None = None
    element_name: str | None = None
    target: str | None = None  # Alias for element_name (cross-tool consistency)
    element_role: str | None = None
    text: str | None = None
    key: str | None = None
    app_name: str | None = None
    script: str | None = None
    region: str | None = None
    force_keystroke: bool = False
    ocr: bool = False
    actions: list[dict] | None = None
    continue_on_error: bool = True
    delay_ms: int = 300
    # Scroll params
    direction: Literal["up", "down", "left", "right"] | None = None
    amount: int = 300
    # Drag drop params
    x2: int | None = None
    y2: int | None = None
    source_element: str | None = None
    target_element: str | None = None
    duration_ms: int = 500
    # Dump UI params
    role_filter: str | None = None
    name_filter: str | None = None
    max_depth: int = 10


class VerifyUiStateRequest(DynamicBaseModel):
    """Structured request for desktop UI state verification."""

    expected_element: str | None = None
    expected_role: str | None = None
    expected_text: str | None = None
    timeout_seconds: int = 5


class QuickCheckScreenRequest(DynamicBaseModel):
    """Structured request for quick screen state checks."""

    check_type: Literal["has_text", "has_element", "is_loaded"] = "is_loaded"
    target: str | None = None
    timeout_seconds: int = 5


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "桌面控制", "en": "Desktop Control"},
    required_benefit="desktop_control",
    args_schema=DesktopControlRequest,
)
async def desktop_control(request: DesktopControlRequest) -> str:
    """
    Control the MacOS desktop - SPEED OPTIMIZED

    SPEED FIRST RULES - Follow these to execute 3x faster:

    RULE 1: KEYBOARD FIRST (Always prefer keyboard over mouse)
      - GOOD: key_press("cmd+w") to close window
      - GOOD: key_press("return") to send message
      - GOOD: key_press("cmd+v") to paste
      - BAD: DON'T click coordinates unless keyboard won't work

    RULE 2: USE BATCH MODE (Execute multiple actions together)
      - GOOD: When: All steps are in THE SAME input field
      - GOOD: Example: [click input -> type -> return] as ONE batch
      - GOOD: Skip verification between steps, verify at the END
      - BAD: DON'T batch across different screens or loading states

    RULE 3: SKIP UNNECESSARY SCREENSHOTS
      - GOOD: In batch: Only screenshot at the START and END
      - BAD: DON'T screenshot after every action

    COMMON SHORTCUTS (Memorize these!)
    - WeChat: return (send), cmd+f (search), cmd+n (new chat)
    - Chrome: cmd+l (address), cmd+t (new tab), cmd+w (close tab)
    - System: cmd+tab (switch app), cmd+space (Spotlight)

    EXAMPLES

    Fast - Send WeChat message (3 actions in 1 batch):
      desktop_control(action="batch", actions=[
          {"action": "click", "element_name": "输入框"},
          {"action": "type_text", "text": "Hello"},
          {"action": "key_press", "key": "return"}
      ])

    Slow - Don't do this (3 separate calls with screenshots):
      desktop_control(action="click") -> screenshot -> verify
      desktop_control(action="type_text") -> screenshot -> verify  
      desktop_control(action="key_press") -> screenshot -> verify

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
            - "batch": Execute multiple actions in sequence. Use for multi-step workflows like: click input -> type text -> press enter. See 'actions' parameter.
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
            If not provided, behavior depends on ENABLE_PARTIAL_SCREENSHOT config:
            - True (default): Automatically captures the current active window region
            - False: Captures the full screen
            If the window bounds cannot be determined, falls back to full screen.
            Examples:
            - Auto-capture current window: region=None (recommended for most cases)
            - Capture specific area: region="500,300,200,100" (from OCR/element bounds)
            - Capture specific window: region="624,102,1195,812" (from get_active_app)
        force_keystroke: If True for type_text, uses slow AppleScript keystroke instead of fast clipboard paste.
        ocr: If True for "screenshot", immediately performs OCR and returns text elements + coordinates.
            NOTE: Coordinates are automatically converted to screen coordinates, even for partial screenshots.
            You can directly use these coordinates with click/double_click actions.
        actions: List of action dicts for batch mode. 
            
            CORRECT USE CASES (Safe for batch):
            - All actions target the SAME input field
            - Pure keyboard sequence: [cmd+f -> type -> return]
            - Known workflow: [click input -> type -> return to send]
            
            DON'T USE BATCH (Use separate calls with verification):
            - Actions that change screen/state
            - Actions that need to wait for loading
            - Actions across different windows
            
            EXAMPLE 1 - WeChat send message (GOOD):
            [
                {"action": "click", "element_name": "输入框"},
                {"action": "type_text", "text": "Hello"},  
                {"action": "key_press", "key": "return"}
            ]
            Result: 1 screenshot at start, 1 at end. Fast!
            
            EXAMPLE 2 - Chrome search (GOOD):
            [
                {"action": "key_press", "key": "cmd+l"},      # Focus address bar
                {"action": "key_press", "key": "cmd+a"},      # Select all
                {"action": "type_text", "text": "google.com"},
                {"action": "key_press", "key": "return"}
            ]
            Result: All keyboard, very fast, no coordinates needed!
            
            EXAMPLE 3 - Form fill (GOOD):
            [
                {"action": "click", "element_name": "用户名"},
                {"action": "type_text", "text": "user@example.com"},
                {"action": "key_press", "key": "tab"},        # Next field
                {"action": "type_text", "text": "password"},
                {"action": "key_press", "key": "return"}      # Submit
            ]
            Result: 5 actions, 1 batch, 2 screenshots total
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
    return await DesktopController.execute(**request.model_dump())


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "验证UI状态", "en": "Verify UI State"},
    args_schema=VerifyUiStateRequest,
)
async def verify_ui_state(request: VerifyUiStateRequest) -> str:
    """
    Verify if a specific UI element or text is present on the screen using AX Tree.
    Use this after 'click' or 'type_text' to ensure the UI responded as expected.

    Args:
        expected_element: Partial name of the UI element to look for.
        expected_role: Optional role of the element (e.g., 'AXWindow', 'AXButton').
        expected_text: Optional text that should be present anywhere in the tree.
        timeout_seconds: (Not currently implemented for polling, but performs one immediate check).
    """
    return await DesktopController.verify_ui_state(**request.model_dump())


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "快速检查屏幕", "en": "Quick Check Screen"},
    args_schema=QuickCheckScreenRequest,
)
async def quick_check_screen(request: QuickCheckScreenRequest) -> str:
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
    return await DesktopController.quick_check_screen(**request.model_dump())
