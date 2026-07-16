import logging
import subprocess
import time
from typing import Any, cast

from app.infrastructure.drivers.macos._workspace import (
    ax_copy_attribute,
    ax_value_point,
    ax_value_size,
    frontmost_application,
)

logger = logging.getLogger(__name__)


def _window_bounds_str(window: Any) -> str:
    pos = ax_copy_attribute(window, "AXPosition")
    size = ax_copy_attribute(window, "AXSize")
    point = ax_value_point(pos)
    extent = ax_value_size(size)
    if point and extent:
        return f"{point[0]},{point[1]},{extent[0]},{extent[1]}"
    return "0,0,0,0"


class AppMixin:
    @classmethod
    def open_app(cls, app_name):
        subprocess.run(["open", "-a", app_name], capture_output=True, check=True)

        start = time.time()
        while time.time() - start < 5:
            current = cls.get_current_app()
            if app_name.lower() in current.get("name", "").lower():
                bounds = current.get("bounds", "0,0,0,0")
                logger.info(f"[MacOSDriver] Focused '{app_name}' with bounds: {bounds}")
                return f"SUCCESS: Activated '{app_name}' at {bounds}"
            time.sleep(0.5)

        current = cls.get_current_app()
        return f"WARNING: Requested '{app_name}' but frontmost is '{current.get('name')}' at {current.get('bounds')}"

    @staticmethod
    def run_applescript(script):
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise RuntimeError(f"AppleScript failed: {result.stderr}")

        logger.info("AppleScript executed successfully")
        return result.stdout.strip()

    @staticmethod
    def get_current_app():
        try:
            import AppKit
            NSWorkspace = cast(Any, getattr(AppKit, "NSWorkspace", None))
            if not NSWorkspace:
                raise ImportError("AppKit symbols not found")

            active_app = frontmost_application()

            if not active_app:
                return {"name": "unknown", "pid": -1, "bounds": "0,0,0,0"}

            app_name = active_app.localizedName() or "unknown"
            pid = active_app.processIdentifier()

            # Get window bounds
            try:
                import HIServices
            except ImportError:
                import Quartz as HIServices

            AXUIElementCopyAttributeValue = cast(Any, getattr(HIServices, "AXUIElementCopyAttributeValue", None))
            AXUIElementCreateApplication = cast(Any, getattr(HIServices, "AXUIElementCreateApplication", None))

            bounds = "0,0,0,0"
            if AXUIElementCopyAttributeValue and AXUIElementCreateApplication:
                app_element = AXUIElementCreateApplication(pid)
                _, windows = AXUIElementCopyAttributeValue(app_element, "AXWindows", None)
                if windows:
                    bounds = _window_bounds_str(windows[0])

            return {"name": app_name, "pid": pid, "bounds": bounds}

        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.debug(f"Native get_current_app failed: {e}")

        try:
            script = (
                'tell application "System Events"\n'
                '    set frontApp to first application process whose frontmost is true\n'
                '    set appName to name of frontApp\n'
                '    try\n'
                '        set winBounds to size of window 1 of frontApp\n'
                '        set winPos to position of window 1 of frontApp\n'
                '        return appName & "|" & (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winBounds) & "," & (item 2 of winBounds)\n'
                '    on error\n'
                '        return appName & "|0,0,0,0"\n'
                '    end try\n'
                'end tell'
            )
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                return {"name": parts[0], "pid": -1, "bounds": parts[1] if len(parts) > 1 else "0,0,0,0"}
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"AppleScript get_current_app failed: {e}")

        return {"name": "unknown", "pid": -1, "bounds": "0,0,0,0"}

    @staticmethod
    def get_active_window() -> dict:
        """
        Get the currently active window information.

        Returns a dict with app_name, window_title, and bounds.
        Falls back to get_current_app() if window title cannot be determined.
        """
        try:
            import AppKit
            NSWorkspace = cast(Any, getattr(AppKit, "NSWorkspace", None))
            if not NSWorkspace:
                raise ImportError("AppKit symbols not found")

            workspace = NSWorkspace.sharedWorkspace()
            if workspace is None:
                raise ImportError("NSWorkspace unavailable")
            active_app = frontmost_application()
            if not active_app:
                return {"app_name": "unknown", "window_title": "", "bounds": "0,0,0,0"}

            app_name = active_app.localizedName() or "unknown"
            pid = active_app.processIdentifier()

            try:
                import HIServices
            except ImportError:
                import Quartz as HIServices

            AXUIElementCopyAttributeValue = cast(Any, getattr(HIServices, "AXUIElementCopyAttributeValue", None))
            AXUIElementCreateApplication = cast(Any, getattr(HIServices, "AXUIElementCreateApplication", None))

            title = ""
            bounds = "0,0,0,0"
            if AXUIElementCopyAttributeValue and AXUIElementCreateApplication:
                app_element = AXUIElementCreateApplication(pid)
                _, windows = AXUIElementCopyAttributeValue(app_element, "AXWindows", None)
                if windows:
                    front_window = windows[0]
                    _, title_value = AXUIElementCopyAttributeValue(front_window, "AXTitle", None)
                    if title_value:
                        title = str(title_value)
                    bounds = _window_bounds_str(front_window)

            return {"app_name": app_name, "window_title": title, "bounds": bounds}
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"Native get_active_window failed: {e}")

        try:
            script = (
                'tell application "System Events"\n'
                '    set frontApp to first application process whose frontmost is true\n'
                '    set appName to name of frontApp\n'
                '    try\n'
                '        set winTitle to name of window 1 of frontApp\n'
                '        set winBounds to size of window 1 of frontApp\n'
                '        set winPos to position of window 1 of frontApp\n'
                '        return appName & ":::" & winTitle & ":::" & (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winBounds) & "," & (item 2 of winBounds)\n'
                '    on error\n'
                '        return appName & "::::::0,0,0,0"\n'
                '    end try\n'
                'end tell'
            )
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(":::")
                return {
                    "app_name": parts[0] if len(parts) > 0 else "unknown",
                    "window_title": parts[1] if len(parts) > 1 else "",
                    "bounds": parts[2] if len(parts) > 2 else "0,0,0,0",
                }
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"AppleScript get_active_window failed: {e}")

        current_app = AppMixin.get_current_app()
        return {
            "app_name": current_app.get("name", "unknown"),
            "window_title": current_app.get("title", ""),
            "bounds": current_app.get("bounds", "0,0,0,0"),
        }

    @staticmethod
    def list_installed_apps():
        script = 'tell application "System Events" to get name of every application process'
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return sorted(line.strip() for line in result.stdout.strip().split(",") if line.strip())
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"list_installed_apps failed: {e}")
        return []
