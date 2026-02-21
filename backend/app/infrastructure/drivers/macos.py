"""
MacOS Driver - Low-level operations for desktop control.
Uses native MacOS commands: screencapture, osascript, open.
"""

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
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGHIDEventTap,
                CGPointMake,
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
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGHIDEventTap,
                kCGMouseEventClickState,
                CGPointMake,
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
    def type_text(text: str) -> None:

        """
        Type the given text using keyboard simulation.

        Args:
            text: Text to type
        """
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

        logger.info(f"Typed text: {text[:20]}...")

    @staticmethod
    def key_press(key: str) -> None:
        """
        Press a key or a combination of keys.

        Args:
            key: Key name or combination (e.g., "enter", "a", "command+a", "shift+tab")
        """
        key_codes = {
            "enter": 36, "return": 36, "escape": 53, "esc": 53,
            "tab": 48, "space": 49, "delete": 51, "backspace": 51,
            "up": 126, "down": 125, "left": 123, "right": 124,
            "command": 55, "shift": 56, "option": 58, "control": 59,
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
    def open_app(app_name: str) -> None:
        """
        Open or focus an application.

        Args:
            app_name: Name of the application (e.g., "Safari", "Terminal")
        """
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            raise RuntimeError(f"Open app failed: {result.stderr}")

        logger.info(f"Opened app: {app_name}")

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

        logger.info(f"AppleScript executed successfully")
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

    @staticmethod
    def dump_ax_tree() -> str:
        """
        Extract the Accessibility (AX) Tree of the frontmost application.
        Returns a JSON-like string of UI elements.
        """
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
                        repeat with menuBar in every menu bar
                            repeat with menuBarItem in (every menu bar item of menuBar)
                                set elName to name of menuBarItem
                                set elRole to role of menuBarItem
                                set elBounds to size of menuBarItem
                                set elPos to position of menuBarItem
                                set elStr to "{'name': '" & elName & "', 'role': '" & elRole & "', 'bounds': [" & (item 1 of elPos) & ", " & (item 2 of elPos) & ", " & (item 1 of elBounds) & ", " & (item 2 of elBounds) & "]},"
                                set jsonOutput to jsonOutput & elStr
                            end repeat
                        end repeat
                    end try

                    -- Capture window elements
                    set windowElements to every UI element of win1
                    repeat with uiElement in windowElements
                        try
                            set elName to name of uiElement
                            if elName is missing value then set elName to description of uiElement
                            set elRole to role of uiElement
                            set elBounds to size of uiElement
                            set elPos to position of uiElement
                            
                            set elStr to "{'name': '" & elName & "', 'role': '" & elRole & "', 'bounds': [" & (item 1 of elPos) & ", " & (item 2 of elPos) & ", " & (item 1 of elBounds) & ", " & (item 2 of elBounds) & "]},"
                            set jsonOutput to jsonOutput & elStr
                            
                            -- One level of sub-elements for buttons/inputs in toolbars
                            repeat with subElement in (every UI element of uiElement)
                                try
                                    set subName to name of subElement
                                    if subName is missing value then set subName to description of subElement
                                    set subRole to role of subElement
                                    set subBounds to size of subElement
                                    set subPos to position of subElement
                                    set subStr to "{'name': '" & subName & "', 'role': '" & subRole & "', 'bounds': [" & (item 1 of subPos) & ", " & (item 2 of subPos) & ", " & (item 1 of subBounds) & ", " & (item 2 of subBounds) & "]},"
                                    set jsonOutput to jsonOutput & subStr
                                end try
                            end repeat
                        end try
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
        """
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set bundleId to bundle identifier of frontApp
            set winTitle to ""
            try
                tell frontApp
                    set winTitle to name of front window
                end tell
            end try
            return appName & ":::" & bundleId & ":::" & winTitle
        end tell
        '''
        try:
            output = MacOSDriver.run_applescript(script)
            parts = output.split(":::")
            if len(parts) >= 3:
                return {
                    "name": parts[0],
                    "bundle_id": parts[1] if parts[1] != "missing value" else parts[0],
                    "title": parts[2]
                }
            return {"name": "unknown", "bundle_id": "unknown", "title": "unknown"}
        except Exception as e:
            logger.error(f"Failed to get current MacOS app: {e}")
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

        Returns:
            True if permissions are granted, False otherwise
        """
        script = '''
        tell application "System Events"
            return UI elements enabled
        end tell
        '''

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )

        return result.returncode == 0 and "true" in result.stdout.lower()


# Singleton instance
macos_driver = MacOSDriver()
