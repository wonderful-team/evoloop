import json
import logging
import subprocess
from typing import Any, cast

from app.infrastructure.drivers.macos._workspace import (
    ax_copy_attribute,
    ax_value_point,
    ax_value_size,
    frontmost_application,
)

logger = logging.getLogger(__name__)


def _ax_value_to_str(value: Any) -> str:
    """Convert an AX attribute value to a safe string.

    AXValue may be a CFString, NSNumber, CGPoint/Size, or other scalar;
    only string-like values are useful as element text.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        s = str(value)
        if s and s != "missing value":
            return s
    except Exception:
        pass
    return ""


class AXMixin:
    @classmethod
    def dump_ax_tree(cls, pid: int | None = None):
        """Dump the AX tree as a JSON string.

        pid: target a specific running process (focus NOT required, verified
        in §四十一); when None, falls back to the frontmost application.
        """
        try:
            import AppKit

            try:
                import HIServices
            except ImportError:
                import Quartz as HIServices

            NSWorkspace = cast(Any, getattr(AppKit, "NSWorkspace", None))
            AXUIElementCopyAttributeValue = cast(Any, getattr(HIServices, "AXUIElementCopyAttributeValue", None))
            AXUIElementCreateApplication = cast(Any, getattr(HIServices, "AXUIElementCreateApplication", None))

            if not all([NSWorkspace, AXUIElementCopyAttributeValue, AXUIElementCreateApplication]):
                raise ImportError("HIServices or AppKit symbols not found")

            kAXChildrenAttribute = "AXChildren"
            kAXDescriptionAttribute = "AXDescription"
            kAXNameAttribute = "AXName"
            kAXPositionAttribute = "AXPosition"
            kAXRoleAttribute = "AXRole"
            kAXSizeAttribute = "AXSize"
            kAXWindowsAttribute = "AXWindows"
            kAXValueAttribute = "AXValue"
            kAXTitleAttribute = "AXTitle"

            if pid is None:
                active_app = frontmost_application()
                if not active_app:
                    return "[]"
                pid = active_app.processIdentifier()
            app_element = AXUIElementCreateApplication(pid)

            error, windows = AXUIElementCopyAttributeValue(app_element, kAXWindowsAttribute, None)
            if error != 0 or not windows:
                return "[]"

            front_window = windows[0]

            def get_element_data(element, depth=0, max_depth=20):
                if depth > max_depth:
                    return None

                data = {}
                _, role = AXUIElementCopyAttributeValue(element, kAXRoleAttribute, None)
                data["role"] = str(role) if role else "AXUnknown"

                _, name = AXUIElementCopyAttributeValue(element, kAXNameAttribute, None)
                if not name:
                    _, name = AXUIElementCopyAttributeValue(element, kAXDescriptionAttribute, None)
                data["name"] = str(name) if name else ""

                # 通用性修复：同时读 AXValue / AXTitle（企微会话等文本常在 value/title 而非 name）
                value_ref = ax_copy_attribute(element, kAXValueAttribute)
                data["value"] = _ax_value_to_str(value_ref)
                title_ref = ax_copy_attribute(element, kAXTitleAttribute)
                data["title"] = str(title_ref) if title_ref else ""

                pos = ax_copy_attribute(element, kAXPositionAttribute)
                size = ax_copy_attribute(element, kAXSizeAttribute)
                point = ax_value_point(pos)
                extent = ax_value_size(size)
                if point and extent:
                    data["bounds"] = [point[0], point[1], extent[0], extent[1]]
                else:
                    data["bounds"] = [0, 0, 0, 0]

                # 剪枝：只对无文本且已深的非叶子角色做截断；
                # AXStaticText 含文本（name/value/title）时保留，避免丢失会话等深层文本。
                has_text = bool(data["name"] or data["value"] or data["title"])
                if depth < max_depth:
                    if depth > 6 and data["role"] == "AXImage":
                        return data
                    if depth > 6 and not has_text and data["role"] in ("AXStaticText", "AXUnknown"):
                        return data

                    _, children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
                    if children:
                        data_children = []
                        for child in children:
                            child_data = get_element_data(child, depth + 1, max_depth)
                            if child_data:
                                data_children.append(child_data)
                        if data_children:
                            data["children"] = data_children

                return data

            flattened = []

            def flatten(node, path="window"):
                item = {
                    "name": node["name"],
                    "role": node["role"],
                    "path": path,
                    "bounds": node["bounds"],
                    "value": node.get("value", ""),
                    "title": node.get("title", ""),
                }
                flattened.append(item)
                if "children" in node:
                    for i, child in enumerate(node["children"]):
                        flatten(child, path=f"{path} > {child['role']} {i + 1}")

            # 遍历所有窗口（不只 windows[0]），合并各窗口的元素树
            for win_idx, win in enumerate(windows):
                tree = get_element_data(win)
                if tree:
                    flatten(tree, path=f"window {win_idx + 1}")
            return json.dumps(flattened)

        except Exception as e:
            logger.error(f"Native dump_ax_tree failed: {e}", exc_info=True)
            logger.debug("Falling back to AppleScript.")

        script = """
        set jsonOutput to "["
        tell application "System Events"
            try
                set frontAppList to every application process whose frontmost is true
                if (count of frontAppList) is 0 then return "[]"
                set frontApp to item 1 of frontAppList

                tell frontApp
                    try
                        set win1 to window 1
                    on error
                        return "[]"
                    end try

                    try
                        set mBarIndex to 1
                        repeat with menuBar in every menu bar
                            set mItemIndex to 1
                            repeat with menuBarItem in (every menu bar item of menuBar)
                                set elName to name of menuBarItem
                                set elRole to role of menuBarItem
                                set elBounds to size of menuBarItem
                                set elPos to position of menuBarItem
                                set elPath to "menu bar item " & mItemIndex & " of menu bar " & mBarIndex
                                set elStr to "{'name': '" & elName & "', 'role': '" & elRole & "', 'path': '" & elPath & "', 'bounds': [" & (item 1 of elPos) & ", " & (item 2 of elPos) & ", " & (item 1 of elBounds) & ", " & (item 2 of elBounds) & "]},"
                                set jsonOutput to jsonOutput & elStr
                                set mItemIndex to mItemIndex + 1
                            end repeat
                            set mBarIndex to mBarIndex + 1
                        end repeat
                    end try

                    set winElIndex to 1
                    set windowElements to every UI element of win1
                    repeat with uiElement in windowElements
                        try
                            set elName to name of uiElement
                            if elName is missing value then set elName to description of uiElement
                            set elRole to role of uiElement
                            set elBounds to size of uiElement
                            set elPos to position of uiElement
                            set elPath to "UI element " & winElIndex & " of window 1"

                            set elStr to "{'name': '" & elName & "', 'role': '" & elRole & "', 'path': '" & elPath & "', 'bounds': [" & (item 1 of elPos) & ", " & (item 2 of elPos) & ", " & (item 1 of elBounds) & ", " & (item 2 of elBounds) & "]},"
                            set jsonOutput to jsonOutput & elStr

                            set subElIndex to 1
                            repeat with subElement in (every UI element of uiElement)
                                try
                                    set subName to name of subElement
                                    if subName is missing value then set subName to description of subElement
                                    set subRole to role of subElement
                                    set subBounds to size of subElement
                                    set subPos to position of subElement
                                    set subPath to "UI element " & subElIndex & " of UI element " & winElIndex & " of window 1"
                                    set subStr to "{'name': '" & subName & "', 'role': '" & subRole & "', 'path': '" & subPath & "', 'bounds': [" & (item 1 of subPos) & ", " & (item 2 of subPos) & ", " & (item 1 of subBounds) & ", " & (item 2 of subBounds) & "]},"
                                    set jsonOutput to jsonOutput & subStr
                                end try
                                set subElIndex to subElIndex + 1
                            end repeat
                        end try
                        set winElIndex to winElIndex + 1
                    end repeat
                end tell
            on error errMsg
                return "Error: " & errMsg
            end try
        end tell
        if length of jsonOutput > 1 then
            set jsonOutput to text 1 thru ((length of jsonOutput) - 1) of jsonOutput
        end if
        return jsonOutput & "]"
        """
        try:
            return cls.run_applescript(script)
        except Exception as e:
            return f"Error: {e}"

    @classmethod
    def perform_ax_action(cls, element_path, action="AXPress"):
        script = f'''
        tell application "System Events"
            try
                set frontAppList to every application process whose frontmost is true
                if (count of frontAppList) is 0 then return "Error: No front app"
                set frontApp to item 1 of frontAppList
                tell frontApp
                    set el to {element_path}
                    if exists el then
                        perform action "{action}" of el
                        return "SUCCESS: Performed {action} on " & "{element_path}"
                    else
                        return "Error: Element not found"
                    end if
                end tell
            on error errMsg
                return "Error: " & errMsg
            end try
        end tell
        '''
        try:
            return cls.run_applescript(script)
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def check_accessibility_permission():
        try:
            try:
                import ApplicationServices
                AXIsProcessTrusted = cast(Any, getattr(ApplicationServices, "AXIsProcessTrusted", None))
            except ImportError:
                import Quartz as ApplicationServices
                AXIsProcessTrusted = cast(Any, getattr(ApplicationServices, "AXIsProcessTrusted", None))

            if AXIsProcessTrusted:
                return AXIsProcessTrusted()
            return False
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)

        script = 'tell application "System Events" to return UI elements enabled'
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "true" in result.stdout.lower()
