"""
Mobile Control Tool - Android device interaction capability via ADB.
Provides the Agent with the ability to see and interact with Android devices.
"""
import os
import asyncio
import logging
from typing import Literal

from app.core.atlas import atlas_engine
from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask
from app.infrastructure.drivers.adb import ADBError, adb_driver

logger = logging.getLogger(__name__)


@evoloop_tool
async def mobile_control(
    action: Literal["screenshot", "tap", "click", "long_press", "swipe", "input_text", "press_key", "dump_ui", "list_devices", "get_info", "list_apps", "open_app", "push", "pull"],
    x: int | None = None,
    y: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    element_name: str | None = None,
    element_role: str | None = None,
    text: str | None = None,
    keycode: int | str | None = None,
    device_id: str | None = None,
    local_path: str | None = None,
    remote_path: str | None = None,
    duration_ms: int = 300,
    wait_after_ms: int = 0,
    ocr: bool = False,
) -> str:

    """
    Control an Android device via ADB - screenshot, tap, click, swipe, and more.
    
    This tool enables both physical (coordinates) and semantic (element name) 
    interaction with a connected Android device.
    
    Args:
        action: The action to perform:
            - "screenshot": Capture the device screen. Returns path to image file.
            - "tap": Tap at coordinates (x, y).
            - "click": Semantic alias for tap. Can use (x, y) OR element_name.
            - "long_press": Long-press at (x, y) OR element_name.
            - "swipe": Swipe from (x, y) to (x2, y2).
            - "input_text": Type text. If element_name given, taps it first.
            - "press_key": Press a key (home, back, enter, etc.).
            - "dump_ui": Get UI hierarchy as XML (for low-level debugging).
            - "list_devices": List connected devices.
            - "list_apps": List installed 3rd-party application packages.
            - "get_info": Get device hardware/OS info.
            - "open_app": Open app by package name (passed in 'text').
            - "push": Push a local file/directory to the device.
            - "pull": Pull a remote file/directory from the device.
        x, y: Primary coordinates for tap/click/swipe.
        x2, y2: End coordinates for swipe.
        element_name: Semantic name/label of the UI element (e.g., "Login", "Search").
        element_role: Optional role/class filter (e.g., "Button", "EditText").
        text: Text to input OR package name for open_app.
        keycode: Key name or code for press_key.
        local_path: Full path on the host Mac (required for push/pull).
        remote_path: Full path on the Android device (required for push/pull).
        device_id: Optional device serial.
        ocr: If True for "screenshot", performs OCR and returns detected elements.
    """
    try:
        async def resolve_element(name: str, role: str | None = None) -> dict | str:
            """Helper to resolve semantic name to coordinates."""
            import asyncio
            # 1. Try Live Accessibility Tree (Fast and Native)
            from app.core.vision.providers.native.android_a11y import android_a11y_provider
            
            # Note: android_a11y_provider.process handles the XML dump Internally
            result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
            if result.success and result.elements:
                import unicodedata
                def normalize_text(t: str) -> str:
                    if not t: return ""
                    return unicodedata.normalize('NFC', str(t)).lower().strip().replace(" ", "").replace("\u3000", "")

                target_norm = normalize_text(name)
                candidates = []
                for el in result.elements:
                    el_text = normalize_text(el.text or "")
                    el_res_id = normalize_text(el.metadata.get("resource_id", ""))
                    el_class = str(el.metadata.get("class", "")).lower()

                    score = 0
                    if el_text == target_norm:
                        score = 100
                    elif target_norm in el_text:
                        score = 50
                    elif target_norm in el_res_id:
                        score = 30
                    
                    if score > 0:
                        if role and role.lower() in el_class:
                            score += 15
                        candidates.append((score, el))
                
                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best_el = candidates[0][1]
                    logger.info(f"[Mobile] Resolved '{name}' via A11y Tree to ({best_el.x}, {best_el.y})")
                    return {"type": "coords", "x": best_el.x, "y": best_el.y}

            # 2. Try App Atlas Fallback (Historical Memory)
            try:
                curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                bundle_id = curr_app.get("package")
                if bundle_id and bundle_id != "unknown":
                    summary = await atlas_engine.store.get_app_summary(bundle_id)
                    if summary and "states" in summary:
                        # For Android, we just scan recent states since window doesn't move 
                        # but elements might be common across states
                        for state_info in summary["states"][:3]: # Check last 3 states
                            full_state = await atlas_engine.store.get_state_detail(bundle_id, state_info["id"])
                            if full_state and "elements" in full_state:
                                for el in full_state["elements"]:
                                    el_label = str(el.get("label") or el.get("text") or "").lower()
                                    if name.lower() in el_label:
                                        # Use coordinates from Atlas as Android screens are static 
                                        # (unlike floating windows on macOS)
                                        if el.get("x") is not None and el.get("y") is not None:
                                            logger.info(f"[Mobile] Resolved '{name}' via Atlas Memory to ({el['x']}, {el['y']})")
                                            return {"type": "coords", "x": el["x"], "y": el["y"]}
            except Exception as e:
                logger.debug(f"[Mobile] Atlas fallback failed: {e}")

            # 3. Try Vision OCR Fallback
            try:
                logger.info(f"[Mobile] Performing OCR fallback for '{name}'")
                temp_img = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
                ocr_result = await vision_engine.process(VisionTask.OCR, temp_img)
                if os.path.exists(temp_img):
                    os.remove(temp_img)
                if ocr_result.success:
                    import unicodedata
                    target_norm = unicodedata.normalize('NFC', name).lower().strip().replace(" ", "").replace("\u3000", "")
                    for el in ocr_result.elements:
                        el_text = unicodedata.normalize('NFC', el.text or "").lower().strip().replace(" ", "").replace("\u3000", "")
                        if target_norm in el_text:
                            logger.info(f"[Mobile] Resolved '{name}' via OCR to ({el.x}, {el.y})")
                            return {"type": "coords", "x": el.x, "y": el.y}
            except Exception as e:
                logger.debug(f"[Mobile] Vision OCR fallback failed: {e}")

            return f"Error: Could not find element with name '{name}' on Android device."

        if action == "list_devices":
            devices = await asyncio.to_thread(adb_driver.list_devices)
            if not devices:
                return "No Android devices connected.\n\nTo connect a device:\n1. Enable Developer Options on your Android device\n2. Enable USB Debugging\n3. Connect via USB and accept the prompt"

            lines = ["Connected devices:"]
            for d in devices:
                status_emoji = "✅" if d["status"] == "device" else "⚠️"
                lines.append(f"  {status_emoji} {d['serial']} ({d['status']}) {d['info']}")

            return "\n".join(lines)

        elif action == "screenshot":
            filepath = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
            result_msg = f"Screenshot saved to: {filepath}"
            
            if ocr:
                try:
                    ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
                    if ocr_result.success and ocr_result.elements:
                        texts = [el.to_prompt_line() for el in ocr_result.elements]
                        if texts:
                            result_msg += "\n\n### OCR Results (Detected Text & Coordinates):\n"
                            result_msg += "\n".join(texts)
                    else:
                        result_msg += "\n\n(OCR requested but no text detected)"
                except Exception as e:
                    logger.error(f"[Mobile] Integrated OCR failed: {e}")
                    result_msg += f"\n\n(OCR Error: {e})"
            
            return result_msg

        elif action in ["tap", "click"]:
            target_x, target_y = x, y
            
            if element_name:
                resolved = await resolve_element(element_name, element_role)
                if isinstance(resolved, str): # Error message
                    return resolved
                target_x = resolved.get("x")
                target_y = resolved.get("y")
            else:
                # Handle relative coordinates
                if any(isinstance(v, float) for v in [target_x, target_y]):
                    screen_w, screen_h = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                    if isinstance(target_x, float) and 0.0 <= target_x <= 1.0:
                        target_x = int(target_x * screen_w)
                    if isinstance(target_y, float) and 0.0 <= target_y <= 1.0:
                        target_y = int(target_y * screen_h)

            if target_x is None or target_y is None:
                return f"Error: 'x' and 'y' coordinates OR 'element_name' are required for {action} action."

            await asyncio.to_thread(adb_driver.tap, target_x, target_y, device_id=device_id)
            result = f"Tapped at ({target_x}, {target_y})" + (f" (resolved from '{element_name}')" if element_name else "")

        elif action == "long_press":
            target_x, target_y = x, y
            if element_name:
                resolved = await resolve_element(element_name, element_role)
                if isinstance(resolved, str): return resolved
                target_x = resolved.get("x")
                target_y = resolved.get("y")
            else:
                # Handle relative coordinates
                if any(isinstance(v, float) for v in [target_x, target_y]):
                    screen_w, screen_h = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                    if isinstance(target_x, float) and 0.0 <= target_x <= 1.0:
                        target_x = int(target_x * screen_w)
                    if isinstance(target_y, float) and 0.0 <= target_y <= 1.0:
                        target_y = int(target_y * screen_h)

            if target_x is None or target_y is None:
                return "Error: 'x' and 'y' coordinates OR 'element_name' are required for long_press action."

            # Long press = swipe to same position with longer duration
            press_duration = duration_ms if duration_ms > 300 else 800
            await asyncio.to_thread(adb_driver.swipe, target_x, target_y, target_x, target_y, duration_ms=press_duration, device_id=device_id)
            result = f"Long-pressed at ({target_x}, {target_y}) for {press_duration}ms" + (f" (resolved from '{element_name}')" if element_name else "")

        elif action == "swipe":
            if any(v is None for v in [x, y, x2, y2]):
                return "Error: 'x', 'y', 'x2', 'y2' are all required for swipe action."

            screen_w, screen_h = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
            # Handle float relative coordinates
            real_x = int(x * screen_w) if isinstance(x, float) and 0.0 <= x <= 1.0 else x
            real_y = int(y * screen_h) if isinstance(y, float) and 0.0 <= y <= 1.0 else y
            real_x2 = int(x2 * screen_w) if isinstance(x2, float) and 0.0 <= x2 <= 1.0 else x2
            real_y2 = int(y2 * screen_h) if isinstance(y2, float) and 0.0 <= y2 <= 1.0 else y2

            await asyncio.to_thread(adb_driver.swipe, real_x, real_y, real_x2, real_y2, duration_ms=duration_ms, device_id=device_id)
            result = f"Swiped from ({real_x}, {real_y}) to ({real_x2}, {real_y2})"

        elif action == "input_text":
            if not text:
                return "Error: 'text' is required for input_text action."

            if element_name:
                # Tap first to focus
                resolved = await resolve_element(element_name, element_role)
                if isinstance(resolved, str): return resolved
                await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                await asyncio.sleep(0.5) # Wait for keyboard/focus
                result_prefix = f"Focused '{element_name}' and input"
            else:
                result_prefix = "Input"

            await asyncio.to_thread(adb_driver.input_text, text, device_id=device_id)
            result = f"{result_prefix} text: {text[:50]}{'...' if len(text) > 50 else ''}"

        elif action == "press_key":
            if keycode is None:
                return "Error: 'keycode' is required for press_key action.\n\nCommon keys: home, back, enter, menu, search, tab, space"

            await asyncio.to_thread(adb_driver.press_key, keycode, device_id=device_id)
            result = f"Pressed key: {keycode}"

        elif action == "get_info":
            info = await asyncio.to_thread(adb_driver.get_system_info, device_id=device_id)
            return f"Device Info: {info}"

        elif action == "list_apps":
            apps = await asyncio.to_thread(adb_driver.list_installed_apps, device_id=device_id)
            return f"Installed Apps: {apps}"

        elif action == "open_app":
            if not text:
                return "Error: 'text' (package name) is required for open_app action."

            # Use 'text' argument as package name
            await asyncio.to_thread(adb_driver.launch_app, text, device_id=device_id)
            result = f"Opened application: {text}"

        elif action == "push":
            if not local_path or not remote_path:
                return "Error: Both 'local_path' and 'remote_path' are required for push action."
            await asyncio.to_thread(adb_driver.push, local_path, remote_path, device_id=device_id)
            result = f"Pushed {local_path} to {remote_path}"

        elif action == "pull":
            if not local_path or not remote_path:
                return "Error: Both 'local_path' and 'remote_path' are required for pull action."
            await asyncio.to_thread(adb_driver.pull, remote_path, local_path, device_id=device_id)
            result = f"Pulled {remote_path} to {local_path}"

        elif action == "dump_ui":
            xml = await asyncio.to_thread(adb_driver.dump_ui, device_id=device_id)

            # Truncate if extreme (200k chars is usually enough for complex apps)
            if len(xml) > 200000:
                xml = xml[:200000] + "\n...(truncated)"

            return f"UI Hierarchy:\n{xml}"

        else:
            return f"Error: Unknown action '{action}'."

        # Wait after action if requested (helps with UI animations)
        if wait_after_ms > 0:
            await asyncio.sleep(wait_after_ms / 1000)
            result += f" (waited {wait_after_ms}ms)"

        return result

    except ADBError as e:
        return f"⚠️ ADB ERROR: {e}"

    except Exception as e:
        logger.error(f"Mobile control error: {e}")
        return f"Error: {str(e)}"

