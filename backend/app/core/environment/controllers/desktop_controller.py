"""
Desktop Controller — Core macOS desktop automation.

Extracted from app.domain.tools.environment.desktop to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/desktop.py thin wrapper).
"""
import ast
import asyncio
import logging
import math
import os
import time

import markdownify

from app.constants import MAX_OUTPUT_LENGTH
from app.core.atlas import atlas_engine, get_bundle_id
from app.core.vision import vision_engine, VisionTask
from app.core.vision.router import VisionRouter
from app.infrastructure.drivers.macos import macos_driver
from app.core.learning.trace_recorder import get_recorder
from app.core.context.manager import ContextManager
from app.core.environment.controllers.utils import (
    cleanup_file,
    normalize_text,
    RecordingContext,
    resolve_element_alias,
    truncate_output,
    BatchExecutor,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────

async def _trigger_atlas_harvest_macos(bundle_id: str):
    """Trigger Atlas harvest for macOS static apps."""
    try:
        from app.core.environment.events import UiTreeObservedEvent, event_bus
        app_info = macos_driver.get_current_app()
        if app_info.get("bundle_id") != bundle_id:
            logger.debug(f"[AtlasHarvest] App mismatch, skipping harvest for {bundle_id}")
            return
        ax_output = macos_driver.dump_ax_tree()
        if not ax_output or "Error" in ax_output:
            logger.debug(f"[AtlasHarvest] Failed to get AX tree for {bundle_id}")
            return
        try:
            elements_data = ast.literal_eval(ax_output.replace("missing value", "None"))
        except Exception:
            logger.debug(f"[AtlasHarvest] Failed to parse AX tree for {bundle_id}")
            return
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
        await atlas_engine.on_ui_tree_observed(event)
        logger.info(f"[AtlasHarvest] Completed harvest for static app: {bundle_id}")
    except Exception as e:
        logger.warning(f"[AtlasHarvest] Failed to harvest for {bundle_id}: {e}")


# ─────────────────────────────────────────────
#  DesktopController
# ─────────────────────────────────────────────

class DesktopController:
    """
    Core macOS desktop automation logic.

    All methods are classmethods (stateless) — hardware state lives in
    the singleton `macos_driver` from infrastructure.
    """

    @classmethod
    async def _resolve_element(cls, name: str, role: str | None = None) -> dict | str:
        """Tri-Engine element resolution: AX Tree → Atlas → OCR."""

        # 1. Try Live Accessibility Tree (Fastest and Native)
        raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
        if not raw_tree or "Error" in raw_tree:
            return f"Error: Failed to dump Accessibility Tree: {raw_tree}"

        try:
            elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
        except Exception as e:
            logger.error(f"[Desktop] Failed to parse AX Tree: {e}")
            return f"Error: AX Tree parsing failed: {e}"

        target_norm = normalize_text(name)
        candidates = []
        for el in elements:
            el_name = normalize_text(el.get("name", ""))
            el_role = str(el.get("role", "")).lower()
            if el_name == target_norm:
                score = 100
            elif target_norm in el_name:
                score = 50
            else:
                continue
            if role and role.lower() in el_role:
                score += 10
            candidates.append((score, el))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_el = candidates[0][1]
            res = {}
            if "path" in best_el:
                res["type"] = "path"
                res["value"] = best_el["path"]
            bounds = best_el.get("bounds", [])
            if len(bounds) == 4:
                res["x"] = int(bounds[0] + bounds[2] / 2)
                res["y"] = int(bounds[1] + bounds[3] / 2)
                if "type" not in res:
                    res["type"] = "coords"
            if res:
                return res

        # 2. Try App Atlas Fallback
        try:
            app_info = macos_driver.get_current_app()
            bundle_id = app_info.get("bundle_id")
            if bundle_id:
                is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos")
                if is_dynamic:
                    strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                    if strategy:
                        infra_elem = strategy.get_infrastructure_element(name)
                        if infra_elem and (infra_elem.get("resource_id") or infra_elem.get("ax_path")):
                            return {"type": "path", "value": infra_elem.get("resource_id") or infra_elem.get("ax_path")}
                        strat = strategy.get_strategy_for(name)
                        if strat:
                            return {"strategy": strat.strategy_type, "parameters": strat.parameters, "source": "atlas_strategy"}
                else:
                    summary = await atlas_engine.store.get_app_summary(bundle_id, platform="macos")
                    if summary and "states" in summary:
                        for state in summary["states"]:
                            full_state = await atlas_engine.store.get_state_detail(bundle_id, state["id"], platform="macos")
                            if full_state and "elements" in full_state:
                                for el in full_state["elements"]:
                                    el_name = str(el.get("label") or el.get("text") or el.get("name") or "").lower()
                                    if name.lower() in el_name:
                                        if el.get("os_identifier") or el.get("ax_path"):
                                            return {"type": "path", "value": el.get("os_identifier") or el.get("ax_path")}
                                        break
        except Exception as e:
            logger.debug(f"[Desktop] Atlas fallback failed: {e}")

        # 3. Try Local Vision OCR
        try:
            app_info = macos_driver.get_current_app()
            bounds_str = app_info.get("bounds")
            win_x, win_y = 0, 0
            if bounds_str:
                try:
                    win_x, win_y, _, _ = map(int, bounds_str.split(","))
                    temp_img = macos_driver.screenshot(region=bounds_str)
                except ValueError:
                    temp_img = macos_driver.screenshot()
            else:
                temp_img = macos_driver.screenshot()

            result = await vision_engine.process(VisionTask.OCR, temp_img)
            target_name = normalize_text(name)
            if result.success:
                cleanup_file(temp_img)
                for el in result.elements:
                    if target_name in normalize_text(el.text):
                        logger.info(f"[Desktop] Resolved '{name}' via OCR → Absolute ({win_x + el.x}, {win_y + el.y})")
                        return {"type": "coords", "x": win_x + el.x, "y": win_y + el.y}
            cleanup_file(temp_img)
        except Exception as e:
            logger.debug(f"[Desktop] Vision OCR fallback failed: {e}")

        logger.error(f"[Desktop] Failed to resolve '{name}'.")
        return f"Error: Could not find element with name '{name}' in live AX tree, Atlas memory, or via local OCR."

    @classmethod
    async def execute(
        cls,
        action: str,
        x: int | None = None,
        y: int | None = None,
        element_name: str | None = None,
        target: str | None = None,
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
        direction: str | None = None,
        amount: int = 300,
        x2: int | None = None,
        y2: int | None = None,
        source_element: str | None = None,
        target_element: str | None = None,
        duration_ms: int = 500,
        role_filter: str | None = None,
        name_filter: str | None = None,
        max_depth: int = 10,
    ) -> str:
        """Execute a desktop action. All business logic lives here."""
        try:
            # Parameter alias
            element_name = resolve_element_alias(target, element_name)

            # Phase 5: Imitation Learning - Trace Recording
            recorder = None
            session_id = ContextManager.get_var("thread_id")
            if session_id:
                recorder = get_recorder(session_id)

            recording_ctx = RecordingContext(
                platform="macos",
                recorder=recorder,
                screenshot_actions=("click", "double_click", "type_text", "key_press", "open_app", "drag_drop")
            )

            async def _record(action_type: str, params: dict):
                async def screenshot_fn():
                    return await asyncio.to_thread(macos_driver.screenshot)

                def context_fn():
                    app_info = macos_driver.get_current_app()
                    return {"app": app_info.get("name"), "bundle_id": app_info.get("bundle_id")}

                await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

            if action == "screenshot":
                app_info = await asyncio.to_thread(macos_driver.get_current_app)
                bundle_id = app_info.get("bundle_id")
                filepath = await asyncio.to_thread(macos_driver.screenshot, region=region, purpose="temp", bundle_id=bundle_id)
                result_msg = f"Screenshot saved to: {filepath}"
                if ocr:
                    try:
                        ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
                        if ocr_result.success and ocr_result.elements:
                            texts = [el.to_prompt_line() for el in ocr_result.elements]
                            if texts:
                                result_msg += "\n\n### OCR Results (Detected Text & Coordinates):\n" + "\n".join(texts)
                        else:
                            result_msg += "\n\n(OCR requested but no text detected)"
                    except Exception as e:
                        result_msg += f"\n\n(OCR Error: {e})"
                return result_msg

            elif action in ["click", "double_click"]:
                target_x, target_y = x, y
                element_path = None

                if element_name:
                    logger.info(f"[Desktop] Attempting to resolve semantic target: {element_name}")
                    resolved = await cls._resolve_element(element_name, element_role)
                    if isinstance(resolved, str):
                        return resolved

                    if resolved.get("source") == "atlas_strategy":
                        strategy_type = resolved.get("strategy")
                        params = resolved.get("parameters", {})
                        if strategy_type == "search_then_click":
                            return (
                                f"[Strategy Required] '{element_name}' is in a dynamic app. "
                                f"Use search approach: {params.get('description', 'Search for the element')}. "
                                f"Direct coordinates are unreliable for this target."
                            )
                        elif strategy_type == "static_click" and params.get("resource_id"):
                            element_path = params.get("resource_id")

                    if resolved.get("type") == "path":
                        element_path = resolved.get("value")
                    target_x = resolved.get("x", target_x)
                    target_y = resolved.get("y", target_y)

                if element_path:
                    res = macos_driver.perform_ax_action(element_path, "AXPress")
                    if "Error" not in res:
                        return f"Natively clicked '{element_name}' without moving the mouse."
                    logger.warning(f"[Desktop] Native AX action failed: {res}. Falling back to physical click.")

                if target_x is None or target_y is None:
                    return f"Error: 'x' and 'y' coordinates OR 'element_name' are required for {action} action."

                screen_w, screen_h = macos_driver.get_screen_size()
                if not (0 <= target_x <= screen_w and 0 <= target_y <= screen_h):
                    return f"Error: Coordinates ({target_x}, {target_y}) are out of screen bounds ({screen_w}x{screen_h})."

                if action == "click":
                    macos_driver.click(target_x, target_y)
                    await _record("click", {"x": target_x, "y": target_y, "element_name": element_name})
                    return f"Visually clicked at ({target_x}, {target_y})" + (f" (resolved from '{element_name}')" if element_name else ".")
                else:
                    macos_driver.double_click(target_x, target_y)
                    await _record("double_click", {"x": target_x, "y": target_y, "element_name": element_name})
                    return f"Visually double-clicked at ({target_x}, {target_y})" + (f" (resolved from '{element_name}')" if element_name else ".")

            elif action == "type_text":
                if not text:
                    return "Error: 'text' is required for type_text action."
                macos_driver.type_text(text, force_keystroke=force_keystroke)
                await _record("type_text", {"text": text, "force_keystroke": force_keystroke})
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
                
                # [Phase 14] Normalize OS-prefixed keys (e.g. 'keyg' -> 'g')
                if key.lower().startswith("key") and len(key) == 4:
                    key = key[3:].lower()
                
                macos_driver.key_press(key)
                await _record("key_press", {"key": key})
                return f"Pressed key: {key}"

            elif action == "open_app":
                if not app_name:
                    return "Error: 'app_name' is required for open_app action."
                bundle_id = await get_bundle_id(app_name)
                is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos") if bundle_id else False
                app_type_str = "DYNAMIC" if is_dynamic else "STATIC"
                icon = "🔄" if is_dynamic else "📍"
                result = macos_driver.open_app(app_name)
                if is_dynamic:
                    strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                    if strategy:
                        logger.info(f"[Desktop] Preloaded strategy for {bundle_id}")
                else:
                    asyncio.create_task(_trigger_atlas_harvest_macos(bundle_id))
                await _record("open_app", {"app_name": app_name, "bundle_id": bundle_id})
                if "Error" not in result:
                    return f"{icon} {result} [{app_type_str}]"
                return result

            elif action == "applescript":
                if not script:
                    return "Error: 'script' is required for applescript action."
                output = macos_driver.run_applescript(script)
                if output:
                    if "</div>" in output or "</body>" in output or "<br>" in output:
                        try:
                            md_output = markdownify.markdownify(output, heading_style="ATX")
                            if md_output.strip():
                                output = f"[Converted from HTML to Markdown]\n{md_output}"
                        except Exception as e:
                            logger.warning(f"Markdown conversion failed: {e}")
                    output = truncate_output(output, MAX_OUTPUT_LENGTH)
                return f"AppleScript executed.\nOutput: {output}" if output else "AppleScript executed successfully."

            elif action == "batch":
                if not actions:
                    return "Error: 'actions' list is required for batch action."
                batch_start = time.time()
                executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)

                async def _exec_action(action_dict: dict) -> str:
                    params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
                    return await cls.execute(action=action_dict.get("action", "unknown"), **params)

                await executor.execute(actions, _exec_action)
                return executor.format_summary(time.time() - batch_start)

            elif action == "scroll":
                if not direction:
                    return "Error: 'direction' (up/down/left/right) is required for scroll."
                try:
                    from Quartz import CGEventCreateScrollWheelEvent, CGEventPost, kCGHIDEventTap
                    if direction == "up":
                        delta_y, delta_x = amount, 0
                    elif direction == "down":
                        delta_y, delta_x = -amount, 0
                    elif direction == "left":
                        delta_x, delta_y = -amount, 0
                    else:
                        delta_x, delta_y = amount, 0
                    event = CGEventCreateScrollWheelEvent(None, 0, 2, delta_y, delta_x)
                    CGEventPost(kCGHIDEventTap, event)
                    await _record("scroll", {"direction": direction, "amount": amount})
                    return f"✅ Scrolled {direction} by {amount}px"
                except ImportError:
                    key_map = {"up": "pageup", "down": "pagedown", "left": "left", "right": "right"}
                    k = key_map.get(direction)
                    if k:
                        presses = max(1, amount // 300)
                        for _ in range(presses):
                            macos_driver.key_press(k)
                            await asyncio.sleep(0.1)
                        await _record("scroll", {"direction": direction, "amount": amount, "method": "key"})
                        return f"✅ Scrolled {direction} (~{amount}px) via key_press"
                    return f"Error: Unable to scroll {direction}"

            elif action == "drag_drop":
                source_x, source_y = x, y
                target_x, target_y = x2, y2
                if source_element:
                    resolved = await cls._resolve_element(source_element)
                    if isinstance(resolved, str):
                        return resolved
                    if "x" in resolved:
                        source_x, source_y = resolved["x"], resolved["y"]
                    else:
                        return f"Error: Could not resolve source element '{source_element}' to coordinates"
                if target_element:
                    resolved = await cls._resolve_element(target_element)
                    if isinstance(resolved, str):
                        return resolved
                    if "x" in resolved:
                        target_x, target_y = resolved["x"], resolved["y"]
                    else:
                        return f"Error: Could not resolve target element '{target_element}' to coordinates"
                if source_x is None or source_y is None or target_x is None or target_y is None:
                    return "Error: Drag-drop requires source and target coordinates, or element names."
                try:
                    from Quartz import (CGEventCreateMouseEvent, CGEventPost, CGPointMake,
                                        kCGEventLeftMouseDown, kCGEventLeftMouseUp,
                                        kCGEventLeftMouseDragged, kCGHIDEventTap)
                    source_point = CGPointMake(source_x, source_y)
                    target_point = CGPointMake(target_x, target_y)
                    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, source_point, 0))
                    await asyncio.sleep(0.05)
                    steps = max(5, duration_ms // 50)
                    for i in range(steps):
                        point = CGPointMake(
                            source_x + (target_x - source_x) * (i + 1) / steps,
                            source_y + (target_y - source_y) * (i + 1) / steps
                        )
                        CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, point, 0))
                        await asyncio.sleep(duration_ms / 1000 / steps)
                    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, target_point, 0))
                    return f"✅ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y}) in {duration_ms}ms"
                except ImportError:
                    return "Error: Drag-drop requires pyobjc-framework-Quartz or cliclick"

            elif action == "dump_ui":
                try:
                    raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
                    if not raw_tree or "Error" in raw_tree:
                        return f"Error: Failed to dump Accessibility Tree: {raw_tree}"
                    elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
                    if not isinstance(elements, list):
                        return "Error: AX Tree format unexpected"
                    filtered_elements = elements
                    if role_filter:
                        filtered_elements = [el for el in filtered_elements if role_filter.lower() in str(el.get("role", "")).lower()]
                    if name_filter:
                        filtered_elements = [el for el in filtered_elements if name_filter.lower() in str(el.get("name", "")).lower()]
                    total = len(elements)
                    filtered = len(filtered_elements)
                    output_lines = [f"UI Hierarchy ({filtered}/{total} elements):", ""]
                    for i, el in enumerate(filtered_elements[:100]):
                        name_val = el.get("name", "") or "(unnamed)"
                        role_val = el.get("role", "Unknown")
                        bounds = el.get("bounds", [])
                        bounds_str = f"[{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}]" if len(bounds) == 4 else "[]"
                        output_lines.append(f"[{i}] {role_val}: '{name_val}' {bounds_str} path={el.get('path', '')}")
                        if len("\n".join(output_lines)) > 5000:
                            output_lines.append(f"\n... ({len(filtered_elements) - i - 1} more elements)")
                            break
                    if len(filtered_elements) > 100:
                        output_lines.append(f"\n... ({len(filtered_elements) - 100} more elements)")
                    return "\n".join(output_lines)
                except Exception as e:
                    return f"Error: dump_ui failed: {e}"

            elif action == "gui_extract":
                filepath = await asyncio.to_thread(macos_driver.screenshot, region=region)
                if not filepath or not os.path.exists(filepath):
                    return "Error: Failed to capture screenshot for GUI extraction."

                try:
                    router = VisionRouter()
                    provider = await router.get_provider(VisionTask.OCR)
                    if not provider:
                        return "Error: No OCR provider available for desktop GUI extraction."

                    result = await provider.process(VisionTask.OCR, filepath)
                    if not result.success or not result.elements:
                        return ""

                    target_x = x if x is not None else 0.5
                    target_y = y if y is not None else 0.5
                    best_match, min_dist = None, float('inf')

                    for el in result.elements:
                        dist = math.sqrt((el.x - (target_x if target_x > 1 else target_x * 1000))**2 +
                                         (el.y - (target_y if target_y > 1 else target_y * 1000))**2)
                        if dist < min_dist:
                            min_dist, best_match = dist, el.text

                    return best_match or ""
                finally:
                    cleanup_file(filepath)

            else:
                return f"Error: Unknown action '{action}'."

        except PermissionError as e:
            return f"⚠️ PERMISSION ERROR: {e}\n\nPlease grant Accessibility access to the terminal/application running this backend."
        except Exception as e:
            logger.error(f"Desktop control error: {e}")
            return f"Error: {str(e)}"

    @classmethod
    async def verify_ui_state(
        cls,
        expected_element: str | None = None,
        expected_role: str | None = None,
        expected_text: str | None = None,
        timeout_seconds: int = 5,
    ) -> str:
        """Verify if a specific UI element or text is present on the screen using AX Tree."""
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
                if expected_element and expected_element.lower() in name:
                    if not expected_role or expected_role.lower() in role:
                        found_element = True
                if expected_text and (expected_text.lower() in name or expected_text.lower() in value):
                    found_text = True
            if expected_element and not found_element:
                return f"Verification FAILED: Element '{expected_element}'" + (f" with role '{expected_role}'" if expected_role else "") + " not found."
            if expected_text and not found_text:
                return f"Verification FAILED: Text '{expected_text}' not found in any UI elements."
            return "Verification SUCCESS: UI state matches expectations."
        except Exception as e:
            return f"Verification Error: {str(e)}"

    @classmethod
    async def quick_check_screen(
        cls,
        check_type: str,
        target: str | None = None,
        timeout_seconds: int = 5,
    ) -> str:
        """Fast screen state check using AX Tree (no LLM)."""
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
                except Exception:
                    await asyncio.sleep(0.5)
                    continue
                if check_type == "is_loaded":
                    if len(elements) > 3:
                        elapsed = time.time() - start_time
                        return f"✅ Screen appears loaded ({len(elements)} UI elements detected in {elapsed:.2f}s)"
                elif check_type == "has_text" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if target_lower in str(el.get("name", "")).lower() or target_lower in str(el.get("value", "")).lower():
                            return f"✅ Found text '{target}' on screen (in {time.time() - start_time:.2f}s)"
                elif check_type == "has_element" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if target_lower in str(el.get("name", "")).lower():
                            bounds = el.get("bounds", [])
                            if len(bounds) == 4:
                                ex, ey = int(bounds[0] + bounds[2] / 2), int(bounds[1] + bounds[3] / 2)
                                return f"✅ Found element '{target}' at ({ex}, {ey}) (in {time.time() - start_time:.2f}s)"
                            return f"✅ Found element '{target}' (in {time.time() - start_time:.2f}s)"
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"[QuickCheck] Error: {e}")
                await asyncio.sleep(0.5)
        elapsed = time.time() - start_time
        if check_type == "is_loaded":
            return f"❌ Screen may not be fully loaded after {elapsed:.1f}s"
        return f"❌ Did not find '{target}' after {elapsed:.1f}s"
