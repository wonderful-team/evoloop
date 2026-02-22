"""
Desktop Control Tool - MacOS desktop interaction capability.
Provides the Agent with the ability to see and interact with the Mac desktop.
"""

import logging
from typing import Literal

import markdownify

from app.core.tools import evoloop_tool
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


@evoloop_tool
async def desktop_control(
    action: Literal["screenshot", "click", "double_click", "type_text", "key_press", "open_app", "applescript", "get_info", "list_apps"],
    x: int | None = None,
    y: int | None = None,
    element_name: str | None = None,
    element_role: str | None = None,
    text: str | None = None,
    key: str | None = None,
    app_name: str | None = None,
    script: str | None = None,
    region: str | None = None,
    force_keystroke: bool = False,
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
            - "applescript": Execute raw AppleScript code.
            - "get_info": Get system hardware and OS environment info.
            - "list_apps": List installed applications in /Applications.
        x: X coordinate for click action.
        y: Y coordinate for click action.
        element_name: Semantic name/label of the UI element to click (e.g., "Login", "Close").
        element_role: Optional role filter for the element (e.g., "AXButton", "AXTextField").
        text: Text to type for type_text action.
        key: Key name or combination for key_press action (e.g., "enter", "tab", "a", "command+a", "shift+tab").
        app_name: Application name for open_app action (e.g., "Safari", "Terminal").
        script: AppleScript code for applescript action.
        region: Optional region "x,y,w,h" for screenshot action.
        force_keystroke: If True for type_text, uses slow AppleScript keystroke instead of fast clipboard paste.
    """
    try:
        # Helper to resolve coordinates or AX path from the Tri-Engine
        async def resolve_element(name: str, role: str | None = None) -> dict | str:
            # 1. Try Live Accessibility Tree (Fastest and Native)
            raw_tree = macos_driver.dump_ax_tree()
            if not raw_tree or "Error" in raw_tree:
                return f"Error: Failed to dump Accessibility Tree: {raw_tree}"

            import ast
            try:
                # The AppleScript returns a string like "[{'name': '...', ...}, ...]"
                # Using ast.literal_eval since it often uses single quotes
                elements = ast.literal_eval(raw_tree)
            except Exception as e:
                logger.error(f"[Desktop] Failed to parse AX Tree: {e}")
                return f"Error: AX Tree parsing failed: {e}"

            for el in elements:
                el_name = str(el.get("name", "")).lower()
                el_role = str(el.get("role", "")).lower()

                name_match = name.lower() in el_name
                role_match = not role or role.lower() in el_role

                if name_match and role_match:
                    res = {}
                    if "path" in el:
                        res["type"] = "path"
                        res["value"] = el["path"]

                    bounds = el.get("bounds", [])
                    if len(bounds) == 4:
                        # Click the center of the element
                        target_x = int(bounds[0] + bounds[2] / 2)
                        target_y = int(bounds[1] + bounds[3] / 2)
                        res["x"] = target_x
                        res["y"] = target_y
                        if "type" not in res:
                            res["type"] = "coords"

                    if res:
                        return res

            # 2. Try App Atlas Fallback (Historical Memory)
            try:
                from app.core.atlas import atlas_engine
                app_info = macos_driver.get_current_app()
                bundle_id = app_info.get("bundle_id")

                if bundle_id:
                    # Query the summary and check states
                    summary = await atlas_engine.store.get_app_summary(bundle_id)
                    if summary and "states" in summary:
                        for state in summary["states"]:
                            # Fetch full state to see elements
                            full_state = await atlas_engine.store.get_state_detail(bundle_id, state["id"])
                            if full_state and "elements" in full_state:
                                for el in full_state["elements"]:
                                    # Fallback covers old (text/name) and new (label) variations
                                    el_name = str(el.get("label") or el.get("text") or el.get("name") or "").lower()
                                    if name.lower() in el_name:
                                        res = {}
                                        if el.get("os_identifier"):
                                            res["type"] = "path"
                                            res["value"] = el["os_identifier"]

                                        bounds = el.get("bounds", {})
                                        if bounds:
                                            res["x"] = int(bounds.get("x", 0) + bounds.get("width", 0) / 2)
                                            res["y"] = int(bounds.get("y", 0) + bounds.get("height", 0) / 2)
                                            if "type" not in res:
                                                res["type"] = "coords"
                                        elif "x" in el and "y" in el:
                                            res["x"] = int(el["x"])
                                            res["y"] = int(el["y"])
                                            if "type" not in res:
                                                res["type"] = "coords"

                                        if res:
                                            return res
            except Exception as e:
                logger.debug(f"[Desktop] Atlas fallback failed: {e}")

            # 3. Try Local Vision OCR (Newly implemented)
            try:
                from app.core.vision.engine import vision_engine
                from app.core.vision.types import VisionTask

                # Take a quick screenshot
                temp_img = macos_driver.screenshot()
                # Run OCR task
                result = await vision_engine.process(VisionTask.OCR, temp_img)
                if result.success:
                    for el in result.elements:
                        if name.lower() in (el.text or "").lower():
                            return {"type": "coords", "x": el.x, "y": el.y}
            except Exception as e:
                logger.debug(f"[Desktop] Vision OCR fallback failed: {e}")

            return f"Error: Could not find element with name '{name}' in live AX tree, Atlas memory, or via local OCR."

        if action == "screenshot":
            filepath = macos_driver.screenshot(region=region)
            return f"Screenshot saved to: {filepath}\n\nUse analyze_image tool to understand what's on screen."

        elif action in ["click", "double_click"]:
            target_x, target_y = x, y
            element_path = None

            if element_name:
                logger.info(f"[Desktop] Attempting to resolve semantic target: {element_name}")
                resolved = await resolve_element(element_name, element_role)
                if isinstance(resolved, str): # Error message
                    return resolved

                if resolved.get("type") == "path":
                    element_path = resolved.get("value")
                    logger.info(f"[Desktop] Resolved '{element_name}' natively to: {element_path}")

                target_x = resolved.get("x", target_x)
                target_y = resolved.get("y", target_y)

                if not element_path:
                    logger.info(f"[Desktop] Resolved '{element_name}' visually to ({target_x}, {target_y})")

            # 1. Try Native Semantic Action Path
            if element_path:
                ax_action = "AXPress" # Double click natively in AX is usually just 'AXPress' again or not strictly defined
                res = macos_driver.perform_ax_action(element_path, ax_action)
                if "Error" not in res:
                    return f"Natively clicked '{element_name}' without moving the mouse."
                else:
                    logger.warning(f"[Desktop] Native AX action failed: {res}. Falling back to physical click.")

            # 2. Fallback to physical coordinate clicks
            if target_x is None or target_y is None:
                return f"Error: 'x' and 'y' coordinates OR 'element_name' are required for {action} action."

            # Validate coordinates
            screen_w, screen_h = macos_driver.get_screen_size()
            if not (0 <= target_x <= screen_w and 0 <= target_y <= screen_h):
                return f"Error: Coordinates ({target_x}, {target_y}) are out of screen bounds ({screen_w}x{screen_h})."

            if action == "click":
                macos_driver.click(target_x, target_y)
                return f"Visually clicked at ({target_x}, {target_y})" + (f" (resolved from '{element_name}')" if element_name else ".")
            else:
                macos_driver.double_click(target_x, target_y)
                return f"Visually double-clicked at ({target_x}, {target_y})" + (f" (resolved from '{element_name}')" if element_name else ".")

        elif action == "type_text":
            if not text:
                return "Error: 'text' is required for type_text action."

            macos_driver.type_text(text, force_keystroke=force_keystroke)
            return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''} (via {'keystroke' if force_keystroke else 'clipboard'})"

        elif action == "get_info":
            info = macos_driver.get_system_info()
            return f"System Info: {info}"

        elif action == "list_apps":
            apps = macos_driver.list_installed_apps()
            return f"Installed Apps: {apps}"

        elif action == "key_press":
            if not key:
                return "Error: 'key' is required for key_press action."

            macos_driver.key_press(key)
            return f"Pressed key: {key}"

        elif action == "open_app":
            if not app_name:
                return "Error: 'app_name' is required for open_app action."

            macos_driver.open_app(app_name)
            return f"Opened application: {app_name}"

        elif action == "applescript":
            if not script:
                return "Error: 'script' is required for applescript action."

            output = macos_driver.run_applescript(script)

            # Intelligent Output Processing
            from app.constants import MAX_OUTPUT_LENGTH

            if output:
                # 1. Detect HTML-like content (common in Notes.app output)
                if "</div>" in output or "</body>" in output or "<br>" in output:
                    try:
                        # Convert HTML to Markdown (strips extensive tags & base64 images usually)
                        # heading_style="ATX" ensures # Header format
                        md_output = markdownify.markdownify(output, heading_style="ATX")
                        if md_output.strip():
                            output = f"[Converted from HTML to Markdown]\n{md_output}"
                    except ImportError:
                        pass # Fallback to raw output if lib missing
                    except Exception as e:
                        logger.warning(f"Markdown conversion failed: {e}")

                # 2. Truncate if still too long
                if len(output) > MAX_OUTPUT_LENGTH:
                    truncated_len = len(output)
                    output = output[:MAX_OUTPUT_LENGTH] + f"\n... [Output truncated, length: {truncated_len}]"

            return f"AppleScript executed.\nOutput: {output}" if output else "AppleScript executed successfully."

        else:
            return f"Error: Unknown action '{action}'."

    except PermissionError as e:
        return f"⚠️ PERMISSION ERROR: {e}\n\nPlease grant Accessibility access to the terminal/application running this backend."

    except Exception as e:
        logger.error(f"Desktop control error: {e}")
        return f"Error: {str(e)}"


@evoloop_tool
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
    try:
        raw_tree = macos_driver.dump_ax_tree()
        if not raw_tree or "Error" in raw_tree:
            return f"Verification Failed: Could not dump AX Tree. {raw_tree}"

        import ast
        elements = ast.literal_eval(raw_tree)

        found_element = False
        found_text = False

        for el in elements:
            name = str(el.get("name", "")).lower()
            role = str(el.get("role", "")).lower()
            value = str(el.get("value", "")).lower()

            if expected_element:
                if expected_element.lower() in name:
                    if not expected_role or expected_role.lower() in role:
                        found_element = True

            if expected_text:
                if expected_text.lower() in name or expected_text.lower() in value:
                    found_text = True

        if expected_element and not found_element:
            return f"Verification FAILED: Element '{expected_element}'" + (f" with role '{expected_role}'" if expected_role else "") + " not found."

        if expected_text and not found_text:
            return f"Verification FAILED: Text '{expected_text}' not found in any UI elements."

        return "Verification SUCCESS: UI state matches expectations."

    except Exception as e:
        return f"Verification Error: {str(e)}"
