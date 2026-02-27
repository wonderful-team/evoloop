"""
MacOS Driver - Low-level operations for desktop control.
Uses native MacOS commands: screencapture, osascript, open.
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class MacOSDriver:
    """
    Low-level MacOS desktop control driver.
    All methods are synchronous and raise exceptions on failure.
    """

    @staticmethod
    def screenshot(region: str | None = None) -> str:
        """
        Capture a screenshot of the screen.

        Args:
            region: Optional region "x,y,w,h" to capture. None = full screen.

        Returns:
            Path to the saved screenshot PNG file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(settings.SCREENSHOTS_DIR, filename)

        cmd = ["screencapture", "-x"]  # -x = silent (no sound)

        if region:
            # Parse "x,y,w,h" format
            try:
                x, y, w, h = map(int, region.split(","))
                cmd.extend(["-R", f"{x},{y},{w},{h}"])
            except ValueError:
                logger.warning(f"Invalid region format: {region}, capturing full screen")

        cmd.append(filepath)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            raise RuntimeError(f"Screenshot failed: {result.stderr}")

        if not os.path.exists(filepath):
            raise RuntimeError("Screenshot file was not created")

        logger.info(f"Screenshot saved: {filepath}")
        return filepath

    @staticmethod
    def click(x: int, y: int) -> None:
        """
        Click at the specified screen coordinates.
        Uses Quartz CGEvent (most reliable) or cliclick as fallback.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        # Method 1: Try Quartz CGEvent (most reliable, no external deps)
        try:
            from Quartz import (
                CGEventCreateMouseEvent,
                CGEventPost,
                CGPointMake,
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGHIDEventTap,
            )

            point = CGPointMake(x, y)

            # Mouse down
            event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            CGEventPost(kCGHIDEventTap, event_down)

            # Small delay between down and up
            time.sleep(0.05)

            # Mouse up
            event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            CGEventPost(kCGHIDEventTap, event_up)

            logger.info(f"Clicked at ({x}, {y}) via CGEvent")
            return

        except ImportError:
            logger.debug("Quartz not available, trying cliclick")
        except Exception as e:
            logger.warning(f"CGEvent click failed: {e}, trying fallback")

        # Method 2: cliclick (if installed)
        cliclick_paths = [
            "/opt/homebrew/bin/cliclick",
            "/usr/local/bin/cliclick",
        ]

        for cliclick_path in cliclick_paths:
            if os.path.exists(cliclick_path):
                try:
                    result = subprocess.run(
                        [cliclick_path, f"c:{x},{y}"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        logger.info(f"Clicked at ({x}, {y}) via cliclick")
                        return
                except Exception as e:
                    logger.warning(f"cliclick failed: {e}")

        # Method 3: AppleScript with mouse move + click current position
        # This is more reliable than "click at"
        script = f'''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
        end tell
        
        do shell script "osascript -e 'tell application \\"System Events\\" to ¬
            tell application process \\"{frontApp}\\" to ¬
            keystroke \\"\\" '"
        '''

        # Actually, the most reliable AppleScript approach is using a helper
        # Since neither CGEvent nor cliclick is available, provide clear error
        raise RuntimeError(
            f"Cannot click at ({x}, {y}). "
            "Please install pyobjc-framework-Quartz: pip install pyobjc-framework-Quartz\n"
            "Or install cliclick: brew install cliclick"
        )

    @staticmethod
    def double_click(x: int, y: int) -> None:
        """
        Double-click at the specified screen coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
        """

        # Try Quartz CGEvent
        try:
            from Quartz import (
                CGEventCreateMouseEvent,
                CGEventPost,
                CGEventSetIntegerValueField,
                CGPointMake,
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGHIDEventTap,
                kCGMouseEventClickState,
            )

            point = CGPointMake(x, y)

            # First click
            event_down1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            CGEventSetIntegerValueField(event_down1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_down1)

            event_up1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            CGEventSetIntegerValueField(event_up1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_up1)

            time.sleep(0.05)

            # Second click
            event_down2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
            CGEventSetIntegerValueField(event_down2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_down2)

            event_up2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
            CGEventSetIntegerValueField(event_up2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_up2)

            logger.info(f"Double-clicked at ({x}, {y}) via CGEvent")
            return

        except ImportError:
            pass

        # Fallback: use cliclick with dc command
        cliclick_paths = ["/opt/homebrew/bin/cliclick", "/usr/local/bin/cliclick"]
        for path in cliclick_paths:
            if os.path.exists(path):
                result = subprocess.run([path, f"dc:{x},{y}"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    logger.info(f"Double-clicked at ({x}, {y}) via cliclick")
                    return

        raise RuntimeError("Double-click requires pyobjc-framework-Quartz or cliclick")

    @staticmethod
    def type_text(text: str, force_keystroke: bool = False) -> None:
        """
        Type the given text using clipboard injection (fast, IME-safe) or keyboard simulation.

        Args:
            text: Text to type
            force_keystroke: If True, uses slow AppleScript keystroke instead of clipboard paste
        """
        if not force_keystroke:
            try:
                # 1. Backup current clipboard
                backup_result = subprocess.run(["pbpaste"], capture_output=True)
                backup_text = backup_result.stdout

                # 2. Inject new text into clipboard
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)

                # 3. Trigger Paste (Cmd + V)
                MacOSDriver.key_press("command+v")

                # 4. Small delay to let the UI process the paste event
                time.sleep(0.1)

                # 5. Restore original clipboard
                subprocess.run(["pbcopy"], input=backup_text)

                logger.info(f"Typed text via clipboard: {text[:20]}...")
                return
            except Exception as e:
                logger.warning(f"Clipboard injection failed: {e}. Falling back to keystroke.")

        # Fallback: Slow keystroke simulation
        # Escape special characters for AppleScript
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "System Events"
            keystroke "{escaped_text}"
        end tell
        '''

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            if "not authorized" in result.stderr.lower() or "not allowed" in result.stderr.lower():
                raise PermissionError(
                    "Accessibility permission required. "
                    "Please grant access in System Settings > Privacy & Security > Accessibility."
                )
            raise RuntimeError(f"Type text failed: {result.stderr}")

        logger.info(f"Typed text via keystroke: {text[:20]}...")

    @staticmethod
    def key_press(key: str) -> None:
        """
        Press a key or a combination of keys.

        Args:
            key: Key name or combination (e.g., "enter", "a", "command+a", "shift+tab")
        """
        key_codes = {
            "enter": 36, "return": 36, "escape": 53, "esc": 53,
            "tab": 48, "space": 49, "delete": 51, "back": 51, "backspace": 51,
            "del": 117, "forward_delete": 117, "caps_lock": 57, "caps": 57,
            "up": 126, "down": 125, "left": 123, "right": 124,
            "pageup": 116, "pagedown": 121, "home": 115, "end": 119,
            "command": 55, "cmd": 55, "shift": 56, "option": 58, "opt": 58, "alt": 58, "control": 59, "ctrl": 59,
            "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
            "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
        }

        # Parse modifiers if any (e.g., "command+a")
        parts = key.lower().split("+")
        main_key = parts[-1]
        modifiers = parts[:-1]

        # Map modifiers to AppleScript names
        mod_map = {
            "command": "command down",
            "cmd": "command down",
            "shift": "shift down",
            "option": "option down",
            "opt": "option down",
            "alt": "option down",
            "control": "control down",
            "ctrl": "control down",
        }

        using_mods = []
        for mod in modifiers:
            if mod in mod_map:
                using_mods.append(mod_map[mod])
            else:
                logger.warning(f"Unknown modifier: {mod}")

        using_clause = ""
        if using_mods:
            using_clause = " using {" + ", ".join(using_mods) + "}"

        # Determine command: keystroke or key code
        if main_key in key_codes:
            # Special keys use "key code"
            script = f'tell application "System Events" to key code {key_codes[main_key]}{using_clause}'
        elif len(main_key) == 1:
            # Alphanumeric keys use "keystroke"
            # Escape " for AppleScript
            escaped_key = main_key.replace('"', '\\"')
            script = f'tell application "System Events" to keystroke "{escaped_key}"{using_clause}'
        else:
            raise ValueError(f"Unknown key: {main_key}. Supported special keys: {list(key_codes.keys())} or single characters.")

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            raise RuntimeError(f"Key press failed: {result.stderr}")

        logger.info(f"Pressed key: {key}")

    @staticmethod
    def open_app(app_name: str) -> str:
        """
        Open or focus an application and WAIT until it is frontmost.
        Returns the window bounds of the activated app.

        Args:
            app_name: Name of the application (e.g., "Safari", "Terminal")
        
        Returns:
            String containing the app info and bounds: "Activated {name} at {x,y,w,h}"
        """
        # 1. Trigger open
        subprocess.run(["open", "-a", app_name], capture_output=True, check=True)
        
        # 2. Poll for focus (up to 5s)
        start = time.time()
        while time.time() - start < 5:
            current = MacOSDriver.get_current_app()
            # Loose match since app_name might be 'Google Chrome' and current['name'] 'Google Chrome'
            if app_name.lower() in current.get("name", "").lower():
                bounds = current.get("bounds", "0,0,0,0")
                logger.info(f"[MacOSDriver] Focused '{app_name}' with bounds: {bounds}")
                return f"SUCCESS: Activated '{app_name}' at {bounds}"
            time.sleep(0.5)
        
        # Fallback: if we can't confirm focus, just return current state
        current = MacOSDriver.get_current_app()
        return f"WARNING: Requested '{app_name}' but frontmost is '{current.get('name')}' at {current.get('bounds')}"

    @staticmethod
    def run_applescript(script: str) -> str:
        """
        Execute raw AppleScript.

        Args:
            script: AppleScript code to execute

        Returns:
            Output from the script execution
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"AppleScript failed: {result.stderr}")

        logger.info("AppleScript executed successfully")
        return result.stdout.strip()

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        """
        Get the main screen resolution.
        """
        script = 'tell application "Finder" to get bounds of window of desktop'
        try:
            output = MacOSDriver.run_applescript(script)
            # Format: "0, 0, 1920, 1080"
            parts = [int(p.strip()) for p in output.split(",")]
            return parts[2], parts[3]
        except Exception:
            return 1920, 1080

    @classmethod
    def get_ui_scale_factor(cls) -> float:
        """
        Calculate the scale factor between logical points and physical pixels.
        Returns 2.0 for Retina, 1.0 for standard displays.
        """
        try:
            # Get logical size
            log_w, _ = cls.get_screen_size()

            # Take a temporary small screenshot to check pixel size
            # Capturing a 1x1 region is enough to get the file but we need the full image
            # metadata. Actually, a full screenshot (cached) is fine.
            screenshot_path = cls.screenshot()
            from PIL import Image
            with Image.open(screenshot_path) as img:
                pixel_w, _ = img.size

            scale = round(pixel_w / log_w, 1) if log_w > 0 else 1.0
            return scale
        except Exception as e:
            logger.debug(f"[MacOSDriver] Failed to calculate scale factor: {e}")
            return 1.0

    @staticmethod
    def dump_ax_tree() -> str:
        """
        Extract the Accessibility (AX) Tree of the frontmost application.
        Uses native Accessibility APIs for high performance.
        Returns a JSON-able list of dictionaries.
        """
        try:
            from AppKit import NSWorkspace
            from HIServices import (
                AXUIElementCopyAttributeValue,
                AXUIElementCreateApplication,
            )
            # Use literal strings for constants to ensure robustness across PyObjC versions
            kAXChildrenAttribute = "AXChildren"
            kAXDescriptionAttribute = "AXDescription"
            kAXNameAttribute = "AXName"
            kAXPositionAttribute = "AXPosition"
            kAXRoleAttribute = "AXRole"
            kAXSizeAttribute = "AXSize"
            kAXWindowsAttribute = "AXWindows"

            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            if not active_app:
                return "[]"

            pid = active_app.processIdentifier()
            app_element = AXUIElementCreateApplication(pid)

            # Get front window
            error, windows = AXUIElementCopyAttributeValue(app_element, kAXWindowsAttribute, None)
            if error != 0 or not windows:
                return "[]"
            
            # Usually the first window in the list is the frontmost/active window
            front_window = windows[0]

            def get_element_data(element, depth=0, max_depth=8):
                if depth > max_depth:
                    return None
                
                data = {}
                # Role
                _, role = AXUIElementCopyAttributeValue(element, kAXRoleAttribute, None)
                data["role"] = str(role) if role else "AXUnknown"
                
                # Name
                _, name = AXUIElementCopyAttributeValue(element, kAXNameAttribute, None)
                if not name:
                    _, name = AXUIElementCopyAttributeValue(element, kAXDescriptionAttribute, None)
                data["name"] = str(name) if name else ""

                # Pos & Size
                _, pos = AXUIElementCopyAttributeValue(element, kAXPositionAttribute, None)
                _, size = AXUIElementCopyAttributeValue(element, kAXSizeAttribute, None)
                
                if pos and size:
                    # pos and size are structs/dicts depending on the wrapper
                    # In many PyObjC environments, they have x, y or are lists
                    try:
                        data["bounds"] = [int(pos.x), int(pos.y), int(size.width), int(size.height)]
                    except AttributeError:
                        # Fallback for different wrapper versions
                        data["bounds"] = [0, 0, 0, 0]
                else:
                    data["bounds"] = [0, 0, 0, 0]

                # Optimization: Only recurse for specific roles or if it's likely a container
                # We skip deep recursion for simple leaf nodes like StaticText or Image unless they are high level
                if depth < max_depth:
                    # Skip recursing into very deep static text nodes
                    if depth > 4 and data["role"] in ["AXStaticText", "AXImage"]:
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

            # Capture tree starting from front window
            tree = get_element_data(front_window)
            if not tree:
                return "[]"

            # Flatten or format to match previous structure (list of elements)
            flattened = []
            
            def flatten(node, path="window 1"):
                # Simplified node for the list
                item = {
                    "name": node["name"],
                    "role": node["role"],
                    "path": path,
                    "bounds": node["bounds"]
                }
                flattened.append(item)
                
                # Append children with path tracking
                if "children" in node:
                    for i, child in enumerate(node["children"]):
                        flatten(child, path=f"{path} > {child['role']} {i+1}")

            flatten(tree)
            return json.dumps(flattened)

        except Exception as e:
            logger.error(f"Native dump_ax_tree failed: {e}", exc_info=True)
            logger.debug("Falling back to AppleScript.")

        # FALLBACK TO APPLESCRIPT
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
                    
                    -- Capture menu bar as well
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

                    -- Capture window elements
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
                            
                            -- One level of sub-elements for buttons/inputs in toolbars
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
            return MacOSDriver.run_applescript(script)
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def perform_ax_action(element_path: str, action: str = "AXPress") -> str:
        """
        Execute an Accessibility action (e.g., click) directly on a UI element path.
        This bypasses the physical mouse and coordinates.
        """
        script = f'''
        tell application "System Events"
            try
                set frontAppList to every application process whose frontmost is true
                if (count of frontAppList) is 0 then return "Error: No front app"
                set frontApp to item 1 of frontAppList
                
                tell frontApp
                    perform action "{action}" of {element_path}
                    return "Success: Performed {action} on {element_path}"
                end tell
            on error errMsg
                return "Error: " & errMsg
            end try
        end tell
        '''
        try:
            return MacOSDriver.run_applescript(script)
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def get_system_info() -> dict:
        """
        Get MacOS system hardware and software info.
        """
        try:
            # OS Version
            os_ver = MacOSDriver.run_applescript('do shell script "sw_vers -productVersion"')
            # Model
            model = MacOSDriver.run_applescript('do shell script "sysctl -n hw.model"')
            # CPU
            cpu = MacOSDriver.run_applescript('do shell script "sysctl -n machdep.cpu.brand_string"')
            # RAM (in GB)
            ram_bytes = MacOSDriver.run_applescript('do shell script "sysctl -n hw.memsize"')
            ram_gb = int(ram_bytes) // (1024**3)

            return {
                "os_version": os_ver,
                "model": model,
                "cpu": cpu,
                "ram_gb": ram_gb,
                "platform": "macos"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_current_app() -> dict:
        """
        Get the currently focused MacOS application and window title.
        Uses AppKit and Quartz for high performance (no osascript).
        """
        try:
            # TRY NATIVE FIRST (FAST)
            from AppKit import NSWorkspace
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowLayer,
                kCGWindowListExcludeDesktopElements,
                kCGWindowListOptionOnScreenOnly,
            )

            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            if not active_app:
                return {"name": "unknown", "bundle_id": "unknown", "title": "unknown"}

            app_name = active_app.localizedName() or "unknown"
            bundle_id = active_app.bundleIdentifier() or "unknown"
            pid = active_app.processIdentifier()

            # Get window title and bounds via Quartz (much faster than osascript)
            win_title = ""
            win_bounds = ""
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID
            )
            if window_list:
                for window in window_list:
                    if window.get("kCGWindowOwnerPID") == pid and window.get("kCGWindowLayer") == 0:
                        win_title = window.get("kCGWindowName", "")
                        bounds = window.get("kCGWindowBounds", {})
                        if bounds:
                            # Format: x,y,w,h
                            win_bounds = f"{int(bounds.get('X', 0))},{int(bounds.get('Y', 0))},{int(bounds.get('Width', 0))},{int(bounds.get('Height', 0))}"
                        break

            return {
                "name": app_name,
                "bundle_id": bundle_id,
                "title": win_title,
                "bounds": win_bounds
            }

        except Exception as e:
            logger.debug(f"Native get_current_app failed: {e}. Falling back to AppleScript.")

        # FALLBACK TO APPLESCRIPT (SLOW)
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set bundleId to bundle identifier of frontApp
            set winTitle to ""
            set winBounds to ""
            try
                tell frontApp
                    set win to window 1
                    set winTitle to name of win
                    set {x, y} to position of win
                    set {w, h} to size of win
                    set winBounds to (x as string) & "," & (y as string) & "," & (w as string) & "," & (h as string)
                end tell
            end try
            return appName & ":::" & bundleId & ":::" & winTitle & ":::" & winBounds
        end tell
        '''
        try:
            output = MacOSDriver.run_applescript(script)
            parts = output.split(":::")
            if len(parts) >= 4:
                return {
                    "name": parts[0],
                    "bundle_id": parts[1] if parts[1] != "missing value" else parts[0],
                    "title": parts[2],
                    "bounds": parts[3]
                }
            elif len(parts) >= 3:
                 return {
                    "name": parts[0],
                    "bundle_id": parts[1] if parts[1] != "missing value" else parts[0],
                    "title": parts[2],
                    "bounds": ""
                }
            return {"name": "unknown", "bundle_id": "unknown", "title": "unknown", "bounds": ""}
        except Exception as e:
            logger.error(f"Failed to get current MacOS app via AppleScript: {e}")
            return {"name": "error", "bundle_id": "error", "title": "error"}

    @staticmethod
    def list_installed_apps() -> list[str]:
        """
        List applications installed in the standard /Applications folder.
        """
        try:
            apps = os.listdir("/Applications")
            return sorted([a.replace(".app", "") for a in apps if a.endswith(".app")])
        except Exception:
            return []

    @staticmethod
    def check_accessibility_permission() -> bool:
        """
        Check if accessibility permissions are granted.
        """
        try:
            from ApplicationServices import AXIsProcessTrusted
            return AXIsProcessTrusted()
        except Exception:
            pass

        # Fallback to osascript
        script = 'tell application "System Events" to return UI elements enabled'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and "true" in result.stdout.lower()


# Singleton instance
macos_driver = MacOSDriver()
