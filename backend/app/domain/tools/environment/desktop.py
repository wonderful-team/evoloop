"""
Desktop Control Tool - MacOS desktop interaction capability.
Provides the Agent with the ability to see and interact with the Mac desktop.
"""
import ast
import asyncio
import logging
import os
import time
from typing import Literal

import markdownify

from app.constants import MAX_OUTPUT_LENGTH
from app.core.atlas import atlas_engine, get_bundle_id
from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


# Phase 6: Helper function to trigger Atlas harvest for macOS
async def _trigger_atlas_harvest_macos(bundle_id: str):
    """Trigger Atlas harvest for macOS static apps."""
    try:
        from app.core.environment.events import UiTreeObservedEvent, event_bus

        # Get current UI info
        app_info = macos_driver.get_current_app()
        if app_info.get("bundle_id") != bundle_id:
            logger.debug(f"[AtlasHarvest] App mismatch, skipping harvest for {bundle_id}")
            return

        # Get AX Tree
        ax_output = macos_driver.dump_ax_tree()
        if not ax_output or "Error" in ax_output:
            logger.debug(f"[AtlasHarvest] Failed to get AX tree for {bundle_id}")
            return

        # Parse elements
        import ast
        try:
            elements_data = ast.literal_eval(ax_output.replace("missing value", "None"))
        except:
            logger.debug(f"[AtlasHarvest] Failed to parse AX tree for {bundle_id}")
            return

        # Create event
        event = type('Event', (), {
            'data': {
                'bundle_id': bundle_id,
                'window_title': app_info.get('title', 'Unknown'),
                'platform': 'macos',
                'screenshot_hash': '',
                'version_hash': ''
            },
            'elements': elements_data
        })()

        # Publish event for Atlas processing
        await atlas_engine.on_ui_tree_observed(event)
        logger.info(f"[AtlasHarvest] Completed harvest for static app: {bundle_id}")

    except Exception as e:
        logger.warning(f"[AtlasHarvest] Failed to harvest for {bundle_id}: {e}")


@evoloop_tool(is_pollable=True)
async def desktop_control(
    action: Literal["screenshot", "click", "double_click", "type_text", "key_press", "open_app", "applescript", "get_info", "list_apps", "batch", "get_active_app", "scroll", "drag_drop", "dump_ui"],
    x: int | None = None,
    y: int | None = None,
    element_name: str | None = None,
    target: str | None = None,  # Alias for element_name (cross-tool consistency)
    element_role: str | None = None,
    text: str | None = None,
    key: str | None = None,
    app_name: str | None = None,
    script: str | None = None,
    region: str | None = None,
    force_keystroke: bool = False,
    ocr: bool = False,
    actions: list[dict] | None = None,
    continue_on_error: bool = True,
    delay_ms: int = 300,
    # Scroll params
    direction: Literal["up", "down", "left", "right"] | None = None,
    amount: int = 300,
    # Drag drop params
    x2: int | None = None,
    y2: int | None = None,
    source_element: str | None = None,
    target_element: str | None = None,
    duration_ms: int = 500,
    # Dump UI params
    role_filter: str | None = None,
    name_filter: str | None = None,
    max_depth: int = 10,
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
            - "applescript": Execute raw AppleScript code. WARNING: Do NOT use this for dynamic apps (WeChat, Chrome, Electron apps) as they lack robust AppleScript support. Use native type_text/click instead.
            - "get_info": Get system hardware and OS environment info.
            - "list_apps": List installed applications in /Applications.
            - "get_active_app": Get the currently focused application's name, title, and window bounds.
            - "scroll": Scroll in the given direction by amount pixels.
            - "drag_drop": Drag from source to target (by element name or coordinates).
            - "dump_ui": Dump the Accessibility Tree as JSON array of UI elements.
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
        force_keystroke: If True for type_text, uses slow AppleScript keystroke instead of fast clipboard paste.
        ocr: If True for "screenshot", immediately performs OCR and returns text elements + coordinates.
        actions: List of action dicts for batch mode. Each dict has "action" and matching params.
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
    try:
        # Parameter alias: target -> element_name (cross-tool consistency)
        if target and not element_name:
            element_name = target

        # Helper to resolve coordinates or AX path from the Tri-Engine
        async def resolve_element(name: str, role: str | None = None) -> dict | str:
            # 1. Try Live Accessibility Tree (Fastest and Native)
            raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
            if not raw_tree or "Error" in raw_tree:
                return f"Error: Failed to dump Accessibility Tree: {raw_tree}"

            try:
                # The AppleScript returns a string like "[{'name': '...', ...}, ...]"
                # Using ast.literal_eval since it often uses single quotes
                elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
            except Exception as e:
                logger.error(f"[Desktop] Failed to parse AX Tree: {e}")
                return f"Error: AX Tree parsing failed: {e}"

            import unicodedata
            def normalize_text(t: str) -> str:
                if not t: return ""
                return unicodedata.normalize('NFC', str(t)).lower().strip().replace(" ", "").replace("\u3000", "")

            target_norm = normalize_text(name)
            
            candidates = []
            for el in elements:
                el_name = normalize_text(el.get("name", ""))
                el_role = str(el.get("role", "")).lower()

                # Scoring and matching
                # 1. Exact match (Highest priority)
                if el_name == target_norm:
                    score = 100
                # 2. Substring match
                elif target_norm in el_name:
                    score = 50
                else:
                    continue

                # Role filter boost
                if role and role.lower() in el_role:
                    score += 10
                
                candidates.append((score, el))

            if candidates:
                # Sort by score descending
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_el = candidates[0][1]
                
                res = {}
                if "path" in best_el:
                    res["type"] = "path"
                    res["value"] = best_el["path"]

                bounds = best_el.get("bounds", [])
                if len(bounds) == 4:
                    target_x = int(bounds[0] + bounds[2] / 2)
                    target_y = int(bounds[1] + bounds[3] / 2)
                    res["x"] = target_x
                    res["y"] = target_y
                    if "type" not in res:
                        res["type"] = "coords"
                
                if res:
                    return res

            # 2. Try App Atlas Fallback (Historical Memory) - Only use ax_path/os_identifier, NOT coordinates
            # Atlas coordinates are absolute and become invalid when window moves
            try:
                app_info = macos_driver.get_current_app()
                bundle_id = app_info.get("bundle_id")

                if bundle_id:
                    # Phase 6: Check if this is a dynamic app
                    is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos")

                    if is_dynamic:
                        # For dynamic apps, try strategy-based resolution
                        strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                        if strategy:
                            # Check infrastructure elements (static like toolbars)
                            infra_elem = strategy.get_infrastructure_element(name)
                            if infra_elem and (infra_elem.get("resource_id") or infra_elem.get("ax_path")):
                                logger.info(f"[Desktop] Resolved '{name}' via Strategy (infrastructure)")
                                return {
                                    "type": "path",
                                    "value": infra_elem.get("resource_id") or infra_elem.get("ax_path")
                                }

                            # Check for strategy
                            strat = strategy.get_strategy_for(name)
                            if strat:
                                logger.info(f"[Desktop] Using strategy '{strat.strategy_type}' for '{name}'")
                                return {
                                    "strategy": strat.strategy_type,
                                    "parameters": strat.parameters,
                                    "source": "atlas_strategy"
                                }

                        # No strategy found, skip Atlas for dynamic apps
                        logger.debug(f"[Desktop] Dynamic app '{bundle_id}' - skipping coordinate fallback")
                    else:
                        # Static app: use normal Atlas fallback
                        summary = await atlas_engine.store.get_app_summary(bundle_id, platform="macos")
                        if summary and "states" in summary:
                            for state in summary["states"]:
                                # Fetch full state to see elements
                                full_state = await atlas_engine.store.get_state_detail(bundle_id, state["id"], platform="macos")
                                if full_state and "elements" in full_state:
                                    for el in full_state["elements"]:
                                        # Fallback covers old (text/name) and new (label) variations
                                        el_name = str(el.get("label") or el.get("text") or el.get("name") or "").lower()
                                        if name.lower() in el_name:
                                            # Only use structural path, NOT bounds (coordinates become stale when window moves)
                                            if el.get("os_identifier") or el.get("ax_path"):
                                                return {
                                                    "type": "path",
                                                    "value": el.get("os_identifier") or el.get("ax_path")
                                                }
                                            # No valid path found, skip Atlas for this element
                                            break
            except Exception as e:
                logger.debug(f"[Desktop] Atlas fallback failed: {e}")

            # 3. Try Local Vision OCR (Newly implemented)
            try:
                # 3a. Get current app bounds for a focused scan
                app_info = macos_driver.get_current_app()
                bounds_str = app_info.get("bounds")
                win_x, win_y = 0, 0
                
                if bounds_str:
                    try:
                        win_x, win_y, _, _ = map(int, bounds_str.split(","))
                        # Take focused screenshot
                        temp_img = macos_driver.screenshot(region=bounds_str)
                        logger.debug(f"[Desktop] Performing focused OCR scan for '{name}' in {app_info.get('name')}")
                    except ValueError:
                        temp_img = macos_driver.screenshot()
                else:
                    temp_img = macos_driver.screenshot()

                # Run OCR task
                result = await vision_engine.process(VisionTask.OCR, temp_img)
                
                import unicodedata
                target_name = unicodedata.normalize('NFC', name).strip().lower().replace(" ", "").replace("\u3000", "")
                
                if result.success:
                    # Cleanup temp image
                    if os.path.exists(temp_img):
                        os.remove(temp_img)
                    
                    for el in result.elements:
                        # Normalize and remove ALL whitespace for robust matching (common in Chinese OCR)
                        el_text_raw = (el.text or "")
                        el_text = unicodedata.normalize('NFC', el_text_raw).strip().lower().replace(" ", "").replace("\u3000", "")
                        
                        # Use substring match
                        if target_name in el_text:
                            # Adjust relative coordinates to absolute screen coordinates
                            logger.info(f"[Desktop] Resolved '{name}' via OCR at relative ({el.x}, {el.y}) -> Absolute ({win_x + el.x}, {win_y + el.y})")
                            return {"type": "coords", "x": win_x + el.x, "y": win_y + el.y}
                
                if os.path.exists(temp_img):
                    os.remove(temp_img)
            except Exception as e:
                logger.debug(f"[Desktop] Vision OCR fallback failed: {e}")

            logger.error(f"[Desktop] Failed to resolve '{name}'.")
            return f"Error: Could not find element with name '{name}' in live AX tree, Atlas memory, or via local OCR."

        if action == "screenshot":
            # Get current app info for proper storage organization
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            bundle_id = app_info.get("bundle_id")
            filepath = await asyncio.to_thread(
                macos_driver.screenshot,
                region=region,
                purpose="temp",
                bundle_id=bundle_id
            )
            result_msg = f"Screenshot saved to: {filepath}"

            if ocr:
                try:
                    ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
                    if ocr_result.success and ocr_result.elements:
                        texts = []
                        for el in ocr_result.elements:
                            # Use the to_prompt_line format for consistency
                            texts.append(el.to_prompt_line())

                        if texts:
                            result_msg += "\n\n### OCR Results (Detected Text & Coordinates):\n"
                            result_msg += "\n".join(texts)
                    else:
                        result_msg += "\n\n(OCR requested but no text detected)"
                except Exception as e:
                    logger.error(f"[Desktop] Integrated OCR failed: {e}")
                    result_msg += f"\n\n(OCR Error: {e})"

            return result_msg

        elif action in ["click", "double_click"]:
            target_x, target_y = x, y
            element_path = None

            if element_name:
                logger.info(f"[Desktop] Attempting to resolve semantic target: {element_name}")
                resolved = await resolve_element(element_name, element_role)
                if isinstance(resolved, str): # Error message
                    return resolved

                # Phase 6: Handle strategy-based resolution for dynamic apps
                if resolved.get("source") == "atlas_strategy":
                    strategy_type = resolved.get("strategy")
                    params = resolved.get("parameters", {})

                    if strategy_type == "search_then_click":
                        # For dynamic content, we need to execute the search strategy
                        # This is a hint to the agent that direct coordinates are unreliable
                        return (
                            f"[Strategy Required] '{element_name}' is in a dynamic app. "
                            f"Use search approach: {params.get('description', 'Search for the element')}. "
                            f"Direct coordinates are unreliable for this target."
                        )
                    elif strategy_type == "static_click" and params.get("resource_id"):
                        # Infrastructure element with known path
                        element_path = params.get("resource_id")
                        logger.info(f"[Desktop] Using infrastructure path from strategy: {element_path}")

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

        elif action == "get_active_app":
            app_info = macos_driver.get_current_app()
            return f"Active Application: {app_info}"

        elif action == "key_press":
            if not key:
                return "Error: 'key' is required for key_press action."

            macos_driver.key_press(key)
            return f"Pressed key: {key}"

        elif action == "open_app":
            if not app_name:
                return "Error: 'app_name' is required for open_app action."

            # Phase 6: Check app type before opening
            # Get bundle ID from app name (Redis -> auto-detect)
            bundle_id = await get_bundle_id(app_name)
            is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos") if bundle_id else False
            app_type_str = "DYNAMIC" if is_dynamic else "STATIC"
            icon = "🔄" if is_dynamic else "📍"
            logger.info(f"[Desktop] Opening {app_type_str} app: {app_name} ({bundle_id})")

            result = macos_driver.open_app(app_name)

            # Phase 6: Post-open actions based on app type
            if is_dynamic:
                # For dynamic apps: preload strategy
                strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                if strategy:
                    logger.info(f"[Desktop] Preloaded strategy for {bundle_id}: {len(strategy.infrastructure)} infrastructure elements")
                else:
                    logger.info(f"[Desktop] No strategy yet for {bundle_id}, will rely on real-time perception")
            else:
                # For static apps: trigger immediate Atlas harvest in background
                logger.info(f"[Desktop] Static app opened, triggering Atlas harvest for {bundle_id}")
                asyncio.create_task(_trigger_atlas_harvest_macos(bundle_id))

            # Append type info to result (always include type marker)
            if "Error" not in result:
                return f"{icon} {result} [{app_type_str}]"
            return result

        elif action == "applescript":
            if not script:
                return "Error: 'script' is required for applescript action."

            output = macos_driver.run_applescript(script)
            if output:
                # 1. Detect HTML-like content (common in Notes.app output)
                if "</div>" in output or "</body>" in output or "<br>" in output:
                    try:
                        md_output = markdownify.markdownify(output, heading_style="ATX")
                        if md_output.strip():
                            output = f"[Converted from HTML to Markdown]\n{md_output}"
                    except Exception as e:
                        logger.warning(f"Markdown conversion failed: {e}")

                # 2. Truncate if still too long
                if len(output) > MAX_OUTPUT_LENGTH:
                    truncated_len = len(output)
                    output = output[:MAX_OUTPUT_LENGTH] + f"\n... [Output truncated, length: {truncated_len}]"

            return f"AppleScript executed.\nOutput: {output}" if output else "AppleScript executed successfully."

        elif action == "batch":
            if not actions:
                return "Error: 'actions' list is required for batch action."

            batch_start = time.time()
            results = []
            total = len(actions)

            logger.info(f"[Batch] Starting {total} actions (continue_on_error={continue_on_error})")

            for i, action_dict in enumerate(actions, 1):
                step_start = time.time()
                step_action = action_dict.get("action", "unknown")

                try:
                    params = {"action": step_action}

                    if step_action in ["click", "double_click"]:
                        params.update({
                            "x": action_dict.get("x"),
                            "y": action_dict.get("y"),
                            "element_name": action_dict.get("element_name"),
                            "element_role": action_dict.get("element_role"),
                        })
                    elif step_action == "type_text":
                        params.update({
                            "text": action_dict.get("text"),
                            "force_keystroke": action_dict.get("force_keystroke", False),
                        })
                    elif step_action == "key_press":
                        params["key"] = action_dict.get("key")
                    elif step_action == "open_app":
                        params["app_name"] = action_dict.get("app_name")
                    elif step_action == "applescript":
                        params["script"] = action_dict.get("script")
                    elif step_action == "screenshot":
                        params.update({
                            "region": action_dict.get("region"),
                            "ocr": action_dict.get("ocr", False),
                        })
                    else:
                        raise ValueError(f"Unknown action '{step_action}'")

                    params = {k: v for k, v in params.items() if v is not None}
                    result = await desktop_control.ainvoke(params)

                    latency = int((time.time() - step_start) * 1000)
                    results.append({
                        "step": i, "action": step_action,
                        "status": "success" if not result.startswith("Error") else "error",
                        "result": result, "latency_ms": latency,
                    })

                except Exception as e:
                    latency = int((time.time() - step_start) * 1000)
                    results.append({
                        "step": i, "action": step_action,
                        "status": "error", "result": str(e), "latency_ms": latency,
                    })
                    if not continue_on_error:
                        break

                if i < total and delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            total_time = time.time() - batch_start
            ok = sum(1 for r in results if r["status"] == "success")
            fail = len(results) - ok

            lines = [
                f"✅ Batch Complete: {ok}/{total} succeeded, {fail} failed ({total_time:.2f}s)",
                "",
            ]
            for r in results:
                icon = "✅" if r["status"] == "success" else "❌"
                lines.append(f"  {icon} Step {r['step']}: {r['action']} ({r['latency_ms']}ms)")
                if r["status"] == "error":
                    lines.append(f"      Error: {r['result'][:100]}")

            return "\n".join(lines)

        elif action == "scroll":
            if not direction:
                return "Error: 'direction' (up/down/left/right) is required for scroll."

            try:
                # Try Quartz CGEvent first (smooth scrolling)
                from Quartz import (
                    CGEventCreateScrollWheelEvent,
                    CGEventPost,
                    kCGHIDEventTap,
                )

                # Map direction to scroll wheel deltas
                # macOS scroll wheel: positive = up/left, negative = down/right
                if direction == "up":
                    delta_y = amount
                    delta_x = 0
                elif direction == "down":
                    delta_y = -amount
                    delta_x = 0
                elif direction == "left":
                    delta_x = -amount
                    delta_y = 0
                else:  # right
                    delta_x = amount
                    delta_y = 0

                # Create and post scroll event
                event = CGEventCreateScrollWheelEvent(None, 0, 2, delta_y, delta_x)
                CGEventPost(kCGHIDEventTap, event)

                logger.info(f"[Desktop] Scrolled {direction} by {amount}px via Quartz")
                return f"✅ Scrolled {direction} by {amount}px"

            except ImportError:
                logger.debug("Quartz not available, falling back to key_press")

                # Fallback: use key_press for page scroll
                key_map = {
                    "up": "pageup",
                    "down": "pagedown",
                    "left": "left",
                    "right": "right"
                }

                key = key_map.get(direction)
                if key:
                    # For page scrolls, approximate how many key presses
                    presses = max(1, amount // 300)  # ~300px per page
                    for _ in range(presses):
                        macos_driver.key_press(key)
                        await asyncio.sleep(0.1)
                    return f"✅ Scrolled {direction} (~{amount}px) via key_press"

                return f"Error: Unable to scroll {direction}"

        elif action == "drag_drop":
            # Resolve source and target coordinates
            source_x, source_y = x, y
            target_x, target_y = x2, y2

            # If element names provided, resolve them
            if source_element:
                resolved = await resolve_element(source_element)
                if isinstance(resolved, str):
                    return resolved  # Error message
                if "x" in resolved:
                    source_x, source_y = resolved["x"], resolved["y"]
                else:
                    return f"Error: Could not resolve source element '{source_element}' to coordinates"

            if target_element:
                resolved = await resolve_element(target_element)
                if isinstance(resolved, str):
                    return resolved  # Error message
                if "x" in resolved:
                    target_x, target_y = resolved["x"], resolved["y"]
                else:
                    return f"Error: Could not resolve target element '{target_element}' to coordinates"

            if source_x is None or source_y is None or target_x is None or target_y is None:
                return "Error: Drag-drop requires source and target coordinates, or element names."

            try:
                # Try Quartz CGEvent for smooth drag
                from Quartz import (
                    CGEventCreateMouseEvent,
                    CGEventPost,
                    CGPointMake,
                    kCGEventLeftMouseDown,
                    kCGEventLeftMouseUp,
                    kCGEventLeftMouseDragged,
                    kCGHIDEventTap,
                )

                source_point = CGPointMake(source_x, source_y)
                target_point = CGPointMake(target_x, target_y)

                # Mouse down at source
                event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, source_point, 0)
                CGEventPost(kCGHIDEventTap, event_down)
                await asyncio.sleep(0.05)

                # Drag with interpolation for smooth movement
                steps = max(5, duration_ms // 50)  # At least 5 steps, or based on duration
                for i in range(steps):
                    interp_x = source_x + (target_x - source_x) * (i + 1) / steps
                    interp_y = source_y + (target_y - source_y) * (i + 1) / steps
                    point = CGPointMake(interp_x, interp_y)
                    event_drag = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, point, 0)
                    CGEventPost(kCGHIDEventTap, event_drag)
                    await asyncio.sleep(duration_ms / 1000 / steps)

                # Mouse up at target
                event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, target_point, 0)
                CGEventPost(kCGHIDEventTap, event_up)

                logger.info(f"[Desktop] Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})")
                return f"✅ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y}) in {duration_ms}ms"

            except ImportError:
                # Fallback: use cliclick if available
                cliclick_paths = [
                    "/opt/homebrew/bin/cliclick",
                    "/usr/local/bin/cliclick",
                ]

                for cliclick_path in cliclick_paths:
                    if os.path.exists(cliclick_path):
                        import subprocess
                        # cliclick dd:x,y,destX,destY,duration
                        result = subprocess.run(
                            [cliclick_path, f"dd:{source_x},{source_y},{target_x},{target_y},{duration_ms}"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            return f"✅ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y}) via cliclick"

                return "Error: Drag-drop requires pyobjc-framework-Quartz or cliclick"

        elif action == "dump_ui":
            """Dump the Accessibility Tree as JSON array of UI elements."""
            try:
                raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
                if not raw_tree or "Error" in raw_tree:
                    return f"Error: Failed to dump Accessibility Tree: {raw_tree}"

                # Parse the AX Tree
                try:
                    elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
                except Exception as e:
                    return f"Error: Failed to parse AX Tree: {e}"

                if not isinstance(elements, list):
                    return "Error: AX Tree format unexpected"

                # Apply filters if specified
                filtered_elements = elements

                if role_filter:
                    filtered_elements = [
                        el for el in filtered_elements
                        if role_filter.lower() in str(el.get("role", "")).lower()
                    ]

                if name_filter:
                    filtered_elements = [
                        el for el in filtered_elements
                        if name_filter.lower() in str(el.get("name", "")).lower()
                    ]

                # Build summary
                total = len(elements)
                filtered = len(filtered_elements)

                # Format output (truncate if too large, similar to mobile dump_ui)
                max_output = 5000  # Limit output size
                output_lines = [f"UI Hierarchy ({filtered}/{total} elements):", ""]

                for i, el in enumerate(filtered_elements[:100]):  # Limit to first 100 elements
                    name = el.get("name", "") or "(unnamed)"
                    role = el.get("role", "Unknown")
                    bounds = el.get("bounds", [])
                    path = el.get("path", "")

                    # Format bounds
                    bounds_str = f"[{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}]" if len(bounds) == 4 else "[]"

                    line = f"[{i}] {role}: '{name}' {bounds_str} path={path}"
                    output_lines.append(line)

                    # Check size limit
                    current_output = "\n".join(output_lines)
                    if len(current_output) > max_output:
                        output_lines.append(f"\n... ({len(filtered_elements) - i - 1} more elements)")
                        break

                if len(filtered_elements) > 100:
                    output_lines.append(f"\n... ({len(filtered_elements) - 100} more elements)")

                result = "\n".join(output_lines)

                # Add filter info
                filter_info = []
                if role_filter:
                    filter_info.append(f"role='{role_filter}'")
                if name_filter:
                    filter_info.append(f"name='{name_filter}'")

                if filter_info:
                    result += f"\n\nFilters applied: {', '.join(filter_info)}"

                return result

            except Exception as e:
                logger.error(f"[Desktop] dump_ui failed: {e}")
                return f"Error: dump_ui failed: {e}"

        else:
            return f"Error: Unknown action '{action}'."

    except PermissionError as e:
        return f"⚠️ PERMISSION ERROR: {e}\n\nPlease grant Accessibility access to the terminal/application running this backend."

    except Exception as e:
        logger.error(f"Desktop control error: {e}")
        return f"Error: {str(e)}"


@evoloop_tool(is_pollable=True)
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
        raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
        if not raw_tree or "Error" in raw_tree:
            return f"Verification Failed: Could not dump AX Tree. {raw_tree}"

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


@evoloop_tool(is_pollable=True)
async def quick_check_screen(
    check_type: Literal["has_text", "has_element", "is_loaded"],
    target: str | None = None,
    timeout_seconds: int = 5,
) -> str:
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

    Example:
        # Instead of analyze_image asking "Is page loaded?"
        quick_check_screen("is_loaded")

        # Instead of analyze_image asking "Do you see 'AI news'?"
        quick_check_screen("has_text", "AI新闻")
    """
    start_time = time.time()
    check_start = time.time()

    while time.time() - check_start < timeout_seconds:
        try:
            raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
            if not raw_tree or "Error" in raw_tree:
                await asyncio.sleep(0.5)
                continue

            try:
                elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
            except:
                await asyncio.sleep(0.5)
                continue

            if check_type == "is_loaded":
                if len(elements) > 3:
                    elapsed = time.time() - start_time
                    return f"✅ Screen appears loaded ({len(elements)} UI elements detected in {elapsed:.2f}s)"

            elif check_type == "has_text" and target:
                target_lower = target.lower()
                for el in elements:
                    name = str(el.get("name", "")).lower()
                    value = str(el.get("value", "")).lower()
                    if target_lower in name or target_lower in value:
                        elapsed = time.time() - start_time
                        return f"✅ Found text '{target}' on screen (in {elapsed:.2f}s)"

            elif check_type == "has_element" and target:
                target_lower = target.lower()
                for el in elements:
                    name = str(el.get("name", "")).lower()
                    if target_lower in name:
                        elapsed = time.time() - start_time
                        bounds = el.get("bounds", [])
                        if len(bounds) == 4:
                            x, y = int(bounds[0] + bounds[2]/2), int(bounds[1] + bounds[3]/2)
                            return f"✅ Found element '{target}' at ({x}, {y}) (in {elapsed:.2f}s)"
                        return f"✅ Found element '{target}' (in {elapsed:.2f}s)"

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.debug(f"[QuickCheck] Error: {e}")
            await asyncio.sleep(0.5)

    elapsed = time.time() - start_time
    if check_type == "is_loaded":
        return f"❌ Screen may not be fully loaded after {elapsed:.1f}s"
    return f"❌ Did not find '{target}' after {elapsed:.1f}s"
