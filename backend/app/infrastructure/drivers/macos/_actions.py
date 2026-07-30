import logging
import os
import subprocess
import time
from typing import Any, cast

logger = logging.getLogger(__name__)


class ActionsMixin:
    @staticmethod
    def click(x, y):
        try:
            import Quartz
            CGEventCreateMouseEvent = cast(Any, getattr(Quartz, "CGEventCreateMouseEvent", None))
            CGEventPost = cast(Any, getattr(Quartz, "CGEventPost", None))
            CGPointMake = cast(Any, getattr(Quartz, "CGPointMake", None))

            if not all([CGEventCreateMouseEvent, CGEventPost, CGPointMake]):
                raise ImportError("Quartz symbols not found")

            kCGHIDEventTap = 0

            point = CGPointMake(x, y)
            # 先移动鼠标到目标位置（Electron 需要物理光标在按钮上）
            move_event = CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, 0)
            CGEventPost(kCGHIDEventTap, move_event)
            time.sleep(0.05)
            event_down = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, 0)
            CGEventPost(kCGHIDEventTap, event_down)
            time.sleep(0.05)
            event_up = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, 0)
            CGEventPost(kCGHIDEventTap, event_up)

            logger.info(f"Clicked at ({x}, {y}) via CGEvent")
            return
        except (ImportError, AttributeError) as e:
            logger.debug(f"Quartz not available or failed: {e}, trying cliclick")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"CGEvent click failed: {e}, trying fallback")

        cliclick_paths = ["/opt/homebrew/bin/cliclick", "/usr/local/bin/cliclick"]
        for cliclick_path in cliclick_paths:
            if os.path.exists(cliclick_path):
                try:
                    result = subprocess.run([cliclick_path, f"c:{x},{y}"], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        logger.info(f"Clicked at ({x}, {y}) via cliclick")
                        return
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"cliclick failed: {e}")

        raise RuntimeError(
            f"Cannot click at ({x}, {y}). "
            "Please install pyobjc-framework-Quartz: pip install pyobjc-framework-Quartz\n"
            "Or install cliclick: brew install cliclick"
        )

    @staticmethod
    def double_click(x, y):
        try:
            import Quartz
            CGEventCreateMouseEvent = cast(Any, getattr(Quartz, "CGEventCreateMouseEvent", None))
            CGEventPost = cast(Any, getattr(Quartz, "CGEventPost", None))
            CGEventSetIntegerValueField = cast(Any, getattr(Quartz, "CGEventSetIntegerValueField", None))
            CGPointMake = cast(Any, getattr(Quartz, "CGPointMake", None))

            if not all([CGEventCreateMouseEvent, CGEventPost, CGEventSetIntegerValueField, CGPointMake]):
                raise ImportError("Quartz symbols not found")

            kCGHIDEventTap = 0
            kCGMouseEventClickState = 1

            point = CGPointMake(x, y)

            # 先移动鼠标
            move_event = CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, 0)
            CGEventPost(kCGHIDEventTap, move_event)
            time.sleep(0.05)
            event_down1 = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, 0)
            CGEventSetIntegerValueField(event_down1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_down1)

            event_up1 = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, 0)
            CGEventSetIntegerValueField(event_up1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_up1)

            time.sleep(0.05)

            event_down2 = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, 0)
            CGEventSetIntegerValueField(event_down2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_down2)

            event_up2 = CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, 0)
            CGEventSetIntegerValueField(event_up2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_up2)

            logger.info(f"Double-clicked at ({x}, {y}) via CGEvent")
            return
        except (ImportError, AttributeError) as e:
            logger.debug(f"Quartz double-click failed: {e}")

        cliclick_paths = ["/opt/homebrew/bin/cliclick", "/usr/local/bin/cliclick"]
        for path in cliclick_paths:
            if os.path.exists(path):
                result = subprocess.run([path, f"dc:{x},{y}"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    logger.info(f"Double-clicked at ({x}, {y}) via cliclick")
                    return

        raise RuntimeError("Double-click requires pyobjc-framework-Quartz or cliclick")

    @classmethod
    def type_text(cls, text, force_keystroke=False):
        if not force_keystroke:
            try:
                backup_result = subprocess.run(["pbpaste"], capture_output=True)
                backup_text = backup_result.stdout

                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)

                cls.key_press("command+v")

                time.sleep(0.1)

                subprocess.run(["pbcopy"], input=backup_text)

                logger.info(f"Typed text via clipboard: {text[:20]}...")
                return
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"Clipboard injection failed: {e}. Falling back to keystroke.")

        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "System Events"
            keystroke "{escaped_text}"
        end tell
        '''

        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            if "not authorized" in result.stderr.lower() or "not allowed" in result.stderr.lower():
                raise PermissionError(
                    "Accessibility permission required. "
                    "Please grant access in System Settings > Privacy & Security > Accessibility."
                )
            raise RuntimeError(f"Type text failed: {result.stderr}")

        logger.info(f"Typed text via keystroke: {text[:20]}...")

    @staticmethod
    def key_press(key):
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

        parts = key.lower().split("+")
        main_key = parts[-1]
        modifiers = parts[:-1]

        mod_map = {
            "command": "command down", "cmd": "command down",
            "shift": "shift down",
            "option": "option down", "opt": "option down", "alt": "option down",
            "control": "control down", "ctrl": "control down",
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

        if main_key in key_codes:
            script = f'tell application "System Events" to key code {key_codes[main_key]}{using_clause}'
        elif len(main_key) == 1:
            escaped_key = main_key.replace('"', '\\"')
            script = f'tell application "System Events" to keystroke "{escaped_key}"{using_clause}'
        else:
            raise ValueError(f"Unknown key: {main_key}. Supported special keys: {list(key_codes.keys())} or single characters.")

        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            raise RuntimeError(f"Key press failed: {result.stderr}")

        logger.info(f"Pressed key: {key}")
