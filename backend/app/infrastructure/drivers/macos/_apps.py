import logging
import os
import plistlib
import re
import subprocess
import time
from typing import Any, cast

from app.infrastructure.drivers.macos._workspace import (
    ax_copy_attribute,
    ax_value_point,
    ax_value_size,
    frontmost_application,
)
from app.utils.text import normalize_compact

logger = logging.getLogger(__name__)

_APP_DIRECTORIES = [
    "/Applications",
    "/System/Applications",
    os.path.expanduser("~/Applications"),
]

_STRINGS_KEYS = ("CFBundleDisplayName", "CFBundleName")


def _preferred_languages() -> list[str]:
    """Return the user's preferred language tags (e.g. ``['zh-Hans-CN']``)."""
    try:
        res = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return re.findall(r'"([^"]+)"', res.stdout) if res.returncode == 0 else []
    except Exception:
        return []


def _lproj_candidates(lang: str) -> list[str]:
    """Map a language tag to plausible ``.lproj`` directory names."""
    parts = lang.split("-")
    candidates = [lang]
    if len(parts) >= 2:
        candidates.append("-".join(parts[:2]))
        candidates.append(f"{parts[0]}_{parts[1]}")
        candidates.append(f"{parts[0]}_{parts[-1]}")
        candidates.append(f"{parts[0]}-{parts[-1]}")
    candidates.append(parts[0])
    return candidates


def _parse_strings_display_name(path: str) -> str | None:
    """Read ``CFBundleDisplayName``/``CFBundleName`` from a ``.strings`` file.

    Handles both quoted and unquoted keys and UTF-8 / UTF-16 encodings.
    """
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return None
    for key in _STRINGS_KEYS:
        m = re.search(rf'"?{re.escape(key)}"?\s*=\s*"(.*?)";', text)
        if m:
            return m.group(1)
    return None


def _bundle_info_name(app_path: str) -> str | None:
    """Base display name from the bundle's ``Info.plist``."""
    try:
        with open(os.path.join(app_path, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException):
        return None
    return info.get("CFBundleDisplayName") or info.get("CFBundleName")


def _localized_display_name(app_path: str, languages: list[str]) -> str | None:
    """Resolve the user-facing localized name for an app bundle."""
    resources = os.path.join(app_path, "Contents", "Resources")
    for lang in languages:
        for candidate in _lproj_candidates(lang):
            strings_path = os.path.join(resources, f"{candidate}.lproj", "InfoPlist.strings")
            if os.path.exists(strings_path):
                name = _parse_strings_display_name(strings_path)
                if name:
                    return name
    return _bundle_info_name(app_path)


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
    def _resolve_app_path(cls, app_name: str) -> str | None:
        """用 mdfind 按显示名查找 app 路径，支持中文名；未命中时直接扫描应用目录。"""
        for query in [
            f"kMDItemDisplayName == '{app_name}'",
            f"kMDItemDisplayName == '*{app_name}*'",
        ]:
            result = subprocess.run(
                ["mdfind", query], capture_output=True, text=True, timeout=5,
            )
            paths = [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".app")]
            if paths:
                return paths[0]
        # 目录扫描兜底：归一化匹配（不依赖 Spotlight 索引）
        needle = normalize_compact(app_name)
        for root in _APP_DIRECTORIES:
            try:
                entries = os.listdir(root)
            except OSError:
                continue
            for entry in entries:
                if not entry.endswith(".app"):
                    continue
                app_path = os.path.join(root, entry)
                candidates = [entry[:-4], _bundle_info_name(app_path)]
                if any(normalize_compact(c) == needle for c in candidates if c):
                    return app_path
        return None

    @classmethod
    def open_app(cls, app_name):
        path = cls._resolve_app_path(app_name)
        if path:
            subprocess.run(["open", path], capture_output=True, check=True)
        else:
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
                return {"name": "unknown", "pid": -1, "bounds": "0,0,0,0", "bundle_id": None, "title": None}

            app_name = active_app.localizedName() or "unknown"
            pid = active_app.processIdentifier()

            try:
                bundle_id = active_app.bundleIdentifier()
            except Exception:
                bundle_id = None

            # Get window bounds + title
            try:
                import HIServices
            except ImportError:
                import Quartz as HIServices

            AXUIElementCopyAttributeValue = cast(Any, getattr(HIServices, "AXUIElementCopyAttributeValue", None))
            AXUIElementCreateApplication = cast(Any, getattr(HIServices, "AXUIElementCreateApplication", None))

            bounds = "0,0,0,0"
            title = None
            if AXUIElementCopyAttributeValue and AXUIElementCreateApplication:
                app_element = AXUIElementCreateApplication(pid)
                _, windows = AXUIElementCopyAttributeValue(app_element, "AXWindows", None)
                if windows:
                    bounds = _window_bounds_str(windows[0])
                    title = ax_copy_attribute(windows[0], "AXTitle")

            return {"name": app_name, "pid": pid, "bounds": bounds, "bundle_id": bundle_id, "title": title}

        except Exception as e:
            logger.debug(f"Native get_current_app failed: {e}", exc_info=True)

        try:
            script = (
                'tell application "System Events"\n'
                "    set frontApp to first application process whose frontmost is true\n"
                "    set appName to name of frontApp\n"
                "    set appId to id of frontApp\n"
                "    try\n"
                "        set winBounds to size of window 1 of frontApp\n"
                "        set winPos to position of window 1 of frontApp\n"
                "        set winTitle to title of window 1 of frontApp\n"
                "        return appName & \"|\" & (item 1 of winPos) & \",\" & (item 2 of winPos) & \",\" & (item 1 of winBounds) & \",\" & (item 2 of winBounds) & \"|\" & appId & \"|\" & winTitle\n"
                "    on error\n"
                "        return appName & \"|0,0,0,0|\" & appId & \"|\"\n"
                "    end try\n"
                "end tell"
            )
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                return {
                    "name": parts[0],
                    "pid": -1,
                    "bounds": parts[1] if len(parts) > 1 else "0,0,0,0",
                    "bundle_id": parts[2] if len(parts) > 2 else None,
                    "title": parts[3] if len(parts) > 3 and parts[3] else None,
                }
        except Exception as e:
            logger.debug(f"AppleScript get_current_app failed: {e}", exc_info=True)

        return {"name": "unknown", "pid": -1, "bounds": "0,0,0,0", "bundle_id": None, "title": None}

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
        except Exception as e:
            logger.debug(f"Native get_active_window failed: {e}", exc_info=True)

        try:
            script = (
                'tell application "System Events"\n'
                "    set frontApp to first application process whose frontmost is true\n"
                "    set appName to name of frontApp\n"
                "    try\n"
                "        set winTitle to name of window 1 of frontApp\n"
                "        set winBounds to size of window 1 of frontApp\n"
                "        set winPos to position of window 1 of frontApp\n"
                '        return appName & ":::" & winTitle & ":::" & (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winBounds) & "," & (item 2 of winBounds)\n'
                "    on error\n"
                '        return appName & "::::::0,0,0,0"\n'
                "    end try\n"
                "end tell"
            )
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(":::")
                return {
                    "app_name": parts[0] if len(parts) > 0 else "unknown",
                    "window_title": parts[1] if len(parts) > 1 else "",
                    "bounds": parts[2] if len(parts) > 2 else "0,0,0,0",
                }
        except Exception as e:
            logger.debug(f"AppleScript get_active_window failed: {e}", exc_info=True)

        current_app = AppMixin.get_current_app()
        return {
            "app_name": current_app.get("name", "unknown"),
            "window_title": current_app.get("title", ""),
            "bounds": current_app.get("bounds", "0,0,0,0"),
        }

    @staticmethod
    def list_installed_apps():
        """List genuinely openable installed apps (app bundles).

        Enumerates ``*.app`` bundles from the standard app directories and
        resolves each to its user-facing display name (localized via the
        preferred-language ``InfoPlist.strings``). Display names are what the
        ``open_app`` tool resolves via ``mdfind`` -> path, so the Agent can
        open them on the first attempt.
        """
        languages = _preferred_languages()
        apps: set[str] = set()
        for root in _APP_DIRECTORIES:
            try:
                entries = os.listdir(root)
            except OSError as e:
                logger.debug("list_installed_apps could not scan %s: %s", root, e)
                continue
            for entry in entries:
                if not entry.endswith(".app"):
                    continue
                app_path = os.path.join(root, entry)
                name = _localized_display_name(app_path, languages)
                apps.add(name or entry[:-4])
        return sorted(apps)
