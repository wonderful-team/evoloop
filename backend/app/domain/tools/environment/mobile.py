"""
Mobile Control Tool - Android device interaction capability via ADB.
Provides the Agent with the ability to see and interact with Android devices.
"""

import logging
from typing import Literal

from app.core.tools import evoloop_tool
from app.domain.tools.environment.drivers.adb import adb_driver, ADBError

logger = logging.getLogger(__name__)


@evoloop_tool
async def mobile_control(
    action: Literal["screenshot", "tap", "long_press", "swipe", "input_text", "press_key", "dump_ui", "list_devices", "get_info", "list_apps", "open_app", "push", "pull"],
    x: int | None = None,
    y: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    text: str | None = None,
    keycode: int | str | None = None,
    device_id: str | None = None,
    local_path: str | None = None,
    remote_path: str | None = None,
    duration_ms: int = 300,
    wait_after_ms: int = 0,
) -> str:

    """
    Control an Android device via ADB - screenshot, tap, swipe, and more.
    
    This tool enables direct interaction with a connected Android device.
    Use in combination with analyze_image for vision-guided automation.
    
    Prerequisites:
    - ADB installed: `brew install android-platform-tools`
    - Device connected via USB with USB Debugging enabled
    
    Args:
        action: The action to perform:
            - "screenshot": Capture the device screen. Returns the path to the image file.
            - "tap": Tap at coordinates (x, y).
            - "swipe": Swipe from (x, y) to (x2, y2).
            - "input_text": Type the given text string.
            - "press_key": Press a key by name or keycode (home, back, enter, etc.).
            - "dump_ui": Get the UI hierarchy as XML for element targeting.
            - "list_devices": List connected devices.
            - "get_info": Get device hardware, OS version, and battery status.
            - "list_apps": List installed 3rd-party application packages.
            - "open_app": Open an application by package name.
            - "push": Push a local file/directory to the device.
            - "pull": Pull a remote file/directory from the device.
        x: X coordinate for tap/swipe.
        y: Y coordinate for tap/swipe.
        x2: End X coordinate for swipe.
        y2: End Y coordinate for swipe.
        text: Text to input for input_text action. Also used as package name for open_app.
        keycode: Key name (home, back, enter) or numeric keycode for press_key action.
        device_id: Optional device serial (required if multiple devices connected).
        local_path: Full path on the host Mac (required for push/pull).
        remote_path: Full path on the Android device (required for push/pull).
        duration_ms: Swipe duration in milliseconds (default: 300).
    
    Returns:
        Success message, file path (for screenshot), or XML (for dump_ui).
    
    Example:
        # List connected devices
        mobile_control(action="list_devices")

        # Open App (using text as package name)
        mobile_control(action="open_app", text="com.tencent.mm")
        
        # Take a screenshot
        mobile_control(action="screenshot")
        
        # Tap on a button
        mobile_control(action="tap", x=540, y=1200)
        
        # Swipe up (scroll down)
        mobile_control(action="swipe", x=540, y=1500, x2=540, y2=500)
        
        # Type text
        mobile_control(action="input_text", text="hello world")
        
        # Press home button
        mobile_control(action="press_key", keycode="home")
    """
    try:
        if action == "list_devices":
            devices = adb_driver.list_devices()
            if not devices:
                return "No Android devices connected.\n\nTo connect a device:\n1. Enable Developer Options on your Android device\n2. Enable USB Debugging\n3. Connect via USB and accept the prompt"
            
            lines = ["Connected devices:"]
            for d in devices:
                status_emoji = "✅" if d["status"] == "device" else "⚠️"
                lines.append(f"  {status_emoji} {d['serial']} ({d['status']}) {d['info']}")
            
            return "\n".join(lines)
        
        elif action == "screenshot":
            filepath = adb_driver.screenshot(device_id=device_id)
            return f"Screenshot saved to: {filepath}\n\nUse analyze_image tool to understand what's on screen."
        
        elif action == "tap":
            if x is None or y is None:
                return "Error: 'x' and 'y' coordinates are required for tap action."
            
            # Validate coordinates
            screen_w, screen_h = adb_driver.get_screen_size(device_id=device_id)
            if not (0 <= x <= screen_w and 0 <= y <= screen_h):
                return f"Error: Coordinates ({x}, {y}) are out of screen bounds ({screen_w}x{screen_h})."
            
            adb_driver.tap(x, y, device_id=device_id)
            result = f"Tapped at ({x}, {y})"
        
        elif action == "long_press":
            # Validate coordinates
            screen_w, screen_h = adb_driver.get_screen_size(device_id=device_id)
            if isinstance(x, float) and 0.0 <= x <= 1.0: x = int(x * screen_w)
            if isinstance(y, float) and 0.0 <= y <= 1.0: y = int(y * screen_h)
            
            # Long press = swipe to same position with longer duration
            press_duration = duration_ms if duration_ms > 300 else 800
            adb_driver.swipe(x, y, x, y, duration_ms=press_duration, device_id=device_id)
            result = f"Long-pressed at ({x}, {y}) for {press_duration}ms."
        
        elif action == "swipe":
            if any(v is None for v in [x, y, x2, y2]):
                return "Error: 'x', 'y', 'x2', 'y2' are all required for swipe action."
            
            screen_w, screen_h = adb_driver.get_screen_size(device_id=device_id)
            if isinstance(x, float) and 0.0 <= x <= 1.0: x = int(x * screen_w)
            if isinstance(y, float) and 0.0 <= y <= 1.0: y = int(y * screen_h)
            if isinstance(x2, float) and 0.0 <= x2 <= 1.0: x2 = int(x2 * screen_w)
            if isinstance(y2, float) and 0.0 <= y2 <= 1.0: y2 = int(y2 * screen_h)
            
            adb_driver.swipe(x, y, x2, y2, duration_ms=duration_ms, device_id=device_id)
            result = f"Swiped from ({x}, {y}) to ({x2}, {y2})"
        
        elif action == "input_text":
            if not text:
                return "Error: 'text' is required for input_text action."
            
            adb_driver.input_text(text, device_id=device_id)
            result = f"Input text: {text[:50]}{'...' if len(text) > 50 else ''}"
        
        elif action == "press_key":
            if keycode is None:
                return "Error: 'keycode' is required for press_key action.\n\nCommon keys: home, back, enter, menu, search, tab, space"
            
            adb_driver.press_key(keycode, device_id=device_id)
            result = f"Pressed key: {keycode}"

        elif action == "get_info":
            info = adb_driver.get_system_info(device_id=device_id)
            return f"Device Info: {info}"

        elif action == "list_apps":
            apps = adb_driver.list_installed_apps(device_id=device_id)
            return f"Installed Apps: {apps}"
        
        elif action == "open_app":
            if not text:
                return "Error: 'text' (package name) is required for open_app action."

            # Use 'text' argument as package name
            adb_driver.launch_app(text, device_id=device_id)
            result = f"Opened application: {text}"

        elif action == "push":
            if not local_path or not remote_path:
                return "Error: Both 'local_path' and 'remote_path' are required for push action."
            adb_driver.push(local_path, remote_path, device_id=device_id)
            result = f"Pushed {local_path} to {remote_path}"

        elif action == "pull":
            if not local_path or not remote_path:
                return "Error: Both 'local_path' and 'remote_path' are required for pull action."
            adb_driver.pull(remote_path, local_path, device_id=device_id)
            result = f"Pulled {remote_path} to {local_path}"

        elif action == "dump_ui":
            xml = adb_driver.dump_ui(device_id=device_id)
            
            # Truncate if extreme (200k chars is usually enough for complex apps)
            if len(xml) > 200000:
                xml = xml[:200000] + "\n...(truncated)"
            
            return f"UI Hierarchy:\n{xml}"
        
        else:
            return f"Error: Unknown action '{action}'."
        
        # Wait after action if requested (helps with UI animations)
        if wait_after_ms > 0:
            import asyncio
            await asyncio.sleep(wait_after_ms / 1000)
            result += f" (waited {wait_after_ms}ms)"
        
        return result
    
    except ADBError as e:
        return f"⚠️ ADB ERROR: {e}"
    
    except Exception as e:
        logger.error(f"Mobile control error: {e}")
        return f"Error: {str(e)}"

