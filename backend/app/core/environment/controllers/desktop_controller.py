"""
Desktop Controller — Core macOS desktop automation.

Extracted from app.domain.tools.environment.desktop to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/desktop.py thin wrapper).
"""
import ast
import asyncio
import functools
import logging
import math
import os
import time
from typing import Any

import markdownify

from app.core.atlas import atlas_engine, get_bundle_id
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.environment.controllers.utils import (
    BatchExecutor,
    RecordingContext,
    resolve_element_alias,
    truncate_output,
)
from app.core.environment.schemas import ElementResolutionResult
from app.core.file import cleanup_file
from app.core.learning.trace_recorder import get_recorder
from app.core.shortcuts import get_shortcut
from app.core.vision import VisionTask, get_vision_router, vision_engine
from app.infrastructure.drivers.macos import macos_driver
from app.utils import (
    ControllerResponse,
    PerceptionsFormatter,
    normalize_text,
    render_template,
)

logger = logging.getLogger(__name__)

MAX_OUTPUT_LENGTH = 60000  # Max characters for tool output before truncation


# ─────────────────────────────────────────────
#  Internal Helpers
# ─────────────────────────────────────────────

async def _trigger_atlas_harvest_macos(bundle_id: str):
    """Trigger Atlas harvest for macOS static apps."""
    try:
        app_info = macos_driver.get_current_app()
        if app_info.get("bundle_id") != bundle_id:
            logger.debug(f"[AtlasHarvest] App mismatch, skipping harvest for {bundle_id}")
            return
        ax_output = macos_driver.dump_ax_tree()
        if not ax_output or "Error" in ax_output:
            logger.debug(f"[AtlasHarvest] Failed to get AX tree for {bundle_id}")
            return
        try:
            elements_data = await _async_literal_eval(ax_output.replace("missing value", "None"))
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
#  Helper Functions
# ─────────────────────────────────────────────

async def _async_literal_eval(data: str) -> Any:
    """Parse string data using ast.literal_eval in a thread pool.
    
    This prevents blocking the event loop when parsing large AX Trees.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(ast.literal_eval, data))


# ─────────────────────────────────────────────
#  DesktopController
# ─────────────────────────────────────────────

class DesktopController:
    """
    Core macOS desktop automation logic.

    All methods are classmethods (stateless) — hardware state lives in
    the singleton `macos_driver` from infrastructure.
    """

    # ─────────────────────────────────────────────
    #  Tri-Engine Resolution (Parallel)
    # ─────────────────────────────────────────────

    @classmethod
    async def _try_ax_tree(cls, name: str, role: str | None = None) -> ElementResolutionResult | None:
        """Try to resolve element using AX Tree. Returns result or None."""
        try:
            raw_tree = await asyncio.wait_for(
                asyncio.to_thread(macos_driver.dump_ax_tree),
                timeout=3.0
            )
            if not raw_tree or "Error" in raw_tree:
                return None

            elements = await _async_literal_eval(raw_tree.replace("missing value", "None"))
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
                res = ElementResolutionResult()
                if "path" in best_el:
                    res.type = "path"
                    res.value = best_el["path"]
                bounds = best_el.get("bounds", [])
                if len(bounds) == 4:
                    res.x = int(bounds[0] + bounds[2] / 2)
                    res.y = int(bounds[1] + bounds[3] / 2)
                    if res.type is None:
                        res.type = "coords"
                if res.type or res.value or res.x is not None:
                    logger.debug(f"[Desktop] AX Tree resolved '{name}': {res.model_dump()}")
                    return res
            return None
        except asyncio.TimeoutError:
            logger.debug(f"[Desktop] AX Tree timeout for '{name}'")
            return None
        except Exception as e:
            logger.debug(f"[Desktop] AX Tree failed for '{name}': {e}")
            return None

    @classmethod
    async def _try_atlas(cls, name: str) -> ElementResolutionResult | None:
        """[DIVIDEND] Try to resolve element using Atlas intelligence."""
        try:
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            bundle_id = app_info.get("bundle_id")
            if not bundle_id:
                return None

            result = await atlas_engine.resolve_spatial_element(bundle_id, name, platform="macos")
            if result:
                if "x" in result and "y" in result:
                    # Prefer coordinates if available
                    return ElementResolutionResult(x=result["x"], y=result["y"], source=result.get("source", "atlas"))
                elif "strategy" in result:
                    return ElementResolutionResult(
                        strategy=result["strategy"],
                        parameters=result.get("parameters", {}),
                        source=result.get("source", "atlas_strategy")
                    )
            return None
        except Exception as e:
            logger.debug(f"[Desktop] Atlas resolution dividend failed: {e}")
            return None

    @classmethod
    async def _try_ocr(cls, name: str) -> ElementResolutionResult | None:
        """Try to resolve element using Vision OCR. Returns result or None."""
        temp_img = None
        try:
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            bounds_str = app_info.get("bounds")
            win_x, win_y = 0, 0

            if bounds_str:
                try:
                    win_x, win_y, _, _ = map(int, bounds_str.split(","))
                    temp_img = await asyncio.to_thread(macos_driver.screenshot, region=bounds_str)
                except ValueError:
                    temp_img = await asyncio.to_thread(macos_driver.screenshot)
            else:
                temp_img = await asyncio.to_thread(macos_driver.screenshot)

            result = await asyncio.wait_for(
                vision_engine.process(VisionTask.OCR, temp_img),
                timeout=5.0
            )

            target_name = normalize_text(name)
            if result.success:
                for el in result.elements:
                    if target_name in normalize_text(el.text):
                        logger.info(f"[Desktop] OCR resolved '{name}' → ({win_x + el.x}, {win_y + el.y})")
                        return ElementResolutionResult(type="coords", x=win_x + el.x, y=win_y + el.y)
            return None
        except asyncio.TimeoutError:
            logger.debug(f"[Desktop] OCR timeout for '{name}'")
            return None
        except Exception as e:
            logger.debug(f"[Desktop] OCR failed for '{name}': {e}")
            return None
        finally:
            if temp_img:
                cleanup_file(temp_img)

    @classmethod
    async def _resolve_element(cls, name: str, role: str | None = None) -> ElementResolutionResult | str:
        """
        Tri-Engine element resolution: AX Tree + Atlas + OCR (Parallel).
        
        All three engines run concurrently with individual timeouts.
        Returns the fastest successful result.
        """
        logger.info(f"[Desktop] Resolving element '{name}' with parallel tri-engine...")
        start_time = time.time()

        # Launch all three engines concurrently
        ax_task = asyncio.create_task(cls._try_ax_tree(name, role))
        atlas_task = asyncio.create_task(cls._try_atlas(name))
        ocr_task = asyncio.create_task(cls._try_ocr(name))

        # Wait for the first successful result
        pending = {ax_task, atlas_task, ocr_task}
        result = None
        completed_sources = []

        while pending:
            # Wait for any task to complete
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                try:
                    res = task.result()
                    # Track which engine completed
                    if task == ax_task:
                        completed_sources.append("AX")
                    elif task == atlas_task:
                        completed_sources.append("Atlas")
                    else:
                        completed_sources.append("OCR")

                    if res:  # Successful resolution
                        result = res
                        # Cancel remaining tasks
                        for p in pending:
                            p.cancel()
                        break
                except Exception as e:
                    logger.debug(f"[Desktop] Engine task failed: {e}")

            if result:
                break

        elapsed = time.time() - start_time

        if result:
            logger.info(f"[Desktop] Resolved '{name}' via {completed_sources[-1]} in {elapsed:.2f}s")
            return result

        logger.error(f"[Desktop] Failed to resolve '{name}' after {elapsed:.2f}s (tried: {completed_sources})")
        return ControllerResponse.error(f"Could not resolve element '{name}'")

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
        max_depth: int | None = None,
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

            # Optimization: Cache app_info within single execute call to avoid repeated system calls
            _cached_app_info = None

            async def _get_cached_app_info():
                nonlocal _cached_app_info
                if _cached_app_info is None:
                    _cached_app_info = await asyncio.to_thread(macos_driver.get_current_app)
                return _cached_app_info

            async def _record(action_type: str, params: dict):
                async def screenshot_fn():
                    return await asyncio.to_thread(macos_driver.screenshot)

                async def context_fn():
                    app_info = await _get_cached_app_info()
                    return {"app": app_info.get("name"), "bundle_id": app_info.get("bundle_id")}

                await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

            if action == "screenshot":
                app_info = await _get_cached_app_info()
                bundle_id = app_info.get("bundle_id")

                # 如果没有提供 region，根据配置决定是否自动使用当前窗口的 bounds
                region_offset_x, region_offset_y = 0, 0
                if region is None:
                    if settings.ENABLE_PARTIAL_SCREENSHOT:
                        # 启用局部截图：自动获取当前窗口 bounds
                        bounds = app_info.get("bounds")
                        if bounds:
                            region = bounds
                            logger.info(f"[Desktop] Auto-capturing current window region: {region}")
                        else:
                            logger.warning("[Desktop] No window bounds available, capturing full screen")
                    else:
                        # 禁用局部截图：使用全屏（region=None）
                        logger.info("[Desktop] Partial screenshot disabled, capturing full screen")

                # 解析 region 获取偏移量（用于 OCR 坐标转换）
                if region:
                    try:
                        rx, ry, _, _ = map(int, region.split(','))
                        region_offset_x, region_offset_y = rx, ry
                    except ValueError:
                        pass

                filepath = await asyncio.to_thread(macos_driver.screenshot, region=region, purpose="temp", bundle_id=bundle_id)
                result_msg = ControllerResponse.screenshot_result(success=True, filename=filepath)
                if ocr:
                    try:
                        ocr_result = await vision_engine.process(VisionTask.OCR, filepath)
                        if ocr_result.success and ocr_result.elements:
                            # 转换 OCR 坐标：相对坐标 → 屏幕坐标
                            elements_for_prompt = []
                            for el in ocr_result.elements:
                                el_dict = el.model_dump()
                                # 如果是局部截图，需要加上 region 的偏移量
                                if region_offset_x or region_offset_y:
                                    el_dict['x'] = el.x + region_offset_x
                                    el_dict['y'] = el.y + region_offset_y
                                    # 记录原始坐标用于调试
                                    el_dict['relative_x'] = el.x
                                    el_dict['relative_y'] = el.y
                                elements_for_prompt.append(el_dict)

                            if region_offset_x or region_offset_y:
                                result_msg += f"\n\n> [!NOTE]\n> Screenshot region: {region}\n> OCR coordinates are converted to screen coordinates."

                            result_msg += "\n\n" + render_template(
                                "core/vision/ocr_results.prompt.j2",
                                platform="macos",
                                elements=elements_for_prompt,
                                total_count=len(ocr_result.elements)
                            )
                        else:
                            result_msg += "\n\n" + ControllerResponse.error("OCR requested but no text detected.")
                    except Exception as e:
                        result_msg += "\n\n" + ControllerResponse.error("OCR Error.", details=str(e))
                return result_msg

            elif action in ["click", "double_click"]:
                # 🚀 SPEED OPTIMIZATION: Check for keyboard shortcut first
                if element_name and action == "click":  # Only for click, not double_click
                    try:
                        app_info = await _get_cached_app_info()
                        bundle_id = app_info.get("bundle_id", "")
                        if shortcut := get_shortcut(bundle_id, element_name):
                            logger.info(f"[Desktop] 🚀 Converting click('{element_name}') to shortcut '{shortcut}'")
                            await asyncio.to_thread(macos_driver.key_press, shortcut)
                            await _record("key_press", {"key": shortcut, "converted_from_click": element_name})
                            return f"Pressed shortcut '{shortcut}' (converted from click on '{element_name}') - Faster!"
                    except Exception as e:
                        logger.debug(f"[Desktop] Shortcut conversion failed: {e}, falling back to click")

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
                            return ControllerResponse.error(
                                f"'{element_name}' is in a dynamic app. Strategy required.",
                                details=f"Use search approach: {params.get('description', 'Search for the element')}. Direct coordinates are unreliable."
                            )
                        elif strategy_type == "static_click" and params.get("resource_id"):
                            element_path = params.get("resource_id")

                    if resolved.get("type") == "path":
                        element_path = resolved.get("value")
                    target_x = resolved.get("x", target_x)
                    target_y = resolved.get("y", target_y)

                if element_path:
                    res = await asyncio.to_thread(macos_driver.perform_ax_action, element_path, "AXPress")
                    if "Error" not in res:
                        return ControllerResponse.success(f"Natively clicked '{element_name}' without moving the mouse.")
                    logger.warning(f"[Desktop] Native AX action failed: {res}. Falling back to physical click.")

                if target_x is None or target_y is None:
                    return ControllerResponse.error(f"'x' and 'y' coordinates OR 'element_name' are required for {action} action.")

                screen_w, screen_h = await asyncio.to_thread(macos_driver.get_screen_size)
                if not (0 <= target_x <= screen_w and 0 <= target_y <= screen_h):
                    return ControllerResponse.error(f"Coordinates ({target_x}, {target_y}) are out of screen bounds ({screen_w}x{screen_h}).")

                if action == "click":
                    await asyncio.to_thread(macos_driver.click, target_x, target_y)
                    await _record("click", {"x": target_x, "y": target_y, "element_name": element_name})
                    return ControllerResponse.tap_result(target_x, target_y, element_name=element_name, success=True)
                else:
                    await asyncio.to_thread(macos_driver.double_click, target_x, target_y)
                    await _record("double_click", {"x": target_x, "y": target_y, "element_name": element_name})
                    return ControllerResponse.success(
                        f"Visually double-clicked at ({target_x}, {target_y})" +
                        (f" (resolved from '{element_name}')" if element_name else ".")
                    )

            elif action == "type_text":
                if not text:
                    return ControllerResponse.missing_param("text")
                await asyncio.to_thread(macos_driver.type_text, text, force_keystroke=force_keystroke)
                await _record("type_text", {"text": text, "force_keystroke": force_keystroke})
                return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''} (via {'keystroke' if force_keystroke else 'clipboard'})"

            elif action == "get_info":
                info = await asyncio.to_thread(macos_driver.get_system_info)
                return ControllerResponse.success("System Info", details=str(info))

            elif action == "list_apps":
                apps = await asyncio.to_thread(macos_driver.list_installed_apps)
                return ControllerResponse.success("Installed Apps", details=str(apps))

            elif action == "get_active_app":
                app_info = await asyncio.to_thread(macos_driver.get_current_app)
                return ControllerResponse.success("Active Application", details=str(app_info))

            elif action == "key_press":
                if not key:
                    return ControllerResponse.missing_param("key")

                # [Phase 14] Normalize OS-prefixed keys (e.g. 'keyg' -> 'g')
                if key.lower().startswith("key") and len(key) == 4:
                    key = key[3:].lower()

                await asyncio.to_thread(macos_driver.key_press, key)
                await _record("key_press", {"key": key})
                return ControllerResponse.success(f"Pressed key: {key}")

            elif action == "open_app":
                if not app_name:
                    return ControllerResponse.missing_param("app_name")
                bundle_id = await get_bundle_id(app_name)
                is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "macos") if bundle_id else False
                app_type_str = "DYNAMIC" if is_dynamic else "STATIC"
                icon = "🔄" if is_dynamic else "📍"
                result = await asyncio.to_thread(macos_driver.open_app, app_name)
                if is_dynamic:
                    strategy = await atlas_engine.get_app_strategy(bundle_id, "macos")
                    if strategy:
                        logger.info(f"[Desktop] Preloaded strategy for {bundle_id}")
                else:
                    asyncio.create_task(_trigger_atlas_harvest_macos(bundle_id))
                await _record("open_app", {"app_name": app_name, "bundle_id": bundle_id})
                if "Error" not in result:
                    return ControllerResponse.success(result, note=f"App Type: {app_type_str}")
                return ControllerResponse.error(result)

            elif action == "applescript":
                if not script:
                    return ControllerResponse.missing_param("script")
                output = await asyncio.to_thread(macos_driver.run_applescript, script)
                if output:
                    if "</div>" in output or "</body>" in output or "<br>" in output:
                        try:
                            md_output = markdownify.markdownify(output, heading_style="ATX")
                            if md_output.strip():
                                output = f"[Converted from HTML to Markdown]\n{md_output}"
                        except Exception as e:
                            logger.warning(f"Markdown conversion failed: {e}")
                    output = truncate_output(output, MAX_OUTPUT_LENGTH)
                if output:
                    return ControllerResponse.success("AppleScript executed.", details=f"Output: {output}")
                return ControllerResponse.success("AppleScript executed successfully.")

            elif action == "batch":
                if not actions:
                    return ControllerResponse.missing_param("actions")
                batch_start = time.time()
                executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)

                async def _exec_action(action_dict: dict) -> str:
                    params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
                    return await cls.execute(action=action_dict.get("action", "unknown"), **params)

                await executor.execute(actions, _exec_action)
                return executor.format_summary(time.time() - batch_start)

            elif action == "scroll":
                if not direction:
                    return ControllerResponse.missing_param("direction")
                try:
                    from Quartz import (
                        CGEventCreateScrollWheelEvent,
                        CGEventPost,
                        kCGHIDEventTap,
                    )
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
                    return ControllerResponse.success(f"Scrolled {direction} by {amount}px.")
                except ImportError:
                    key_map = {"up": "pageup", "down": "pagedown", "left": "left", "right": "right"}
                    k = key_map.get(direction)
                    if k:
                        presses = max(1, amount // 300)
                        for _ in range(presses):
                            await asyncio.to_thread(macos_driver.key_press, k)
                            await asyncio.sleep(0.1)
                        await _record("scroll", {"direction": direction, "amount": amount, "method": "key"})
                        return ControllerResponse.success(f"Scrolled {direction} (~{amount}px) via key_press.")
                    return ControllerResponse.error(f"Unable to scroll {direction}.")

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
                        return ControllerResponse.not_found(source_element, item_type="source element")
                if target_element:
                    resolved = await cls._resolve_element(target_element)
                    if isinstance(resolved, str):
                        return resolved
                    if "x" in resolved:
                        target_x, target_y = resolved["x"], resolved["y"]
                    else:
                        return ControllerResponse.not_found(target_element, item_type="target element")
                if source_x is None or source_y is None or target_x is None or target_y is None:
                    return ControllerResponse.error("Drag-drop requires source and target coordinates, or element names.")
                try:
                    from Quartz import (
                        CGEventCreateMouseEvent,
                        CGEventPost,
                        CGPointMake,
                        kCGEventLeftMouseDown,
                        kCGEventLeftMouseDragged,
                        kCGEventLeftMouseUp,
                        kCGHIDEventTap,
                    )
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
                    return ControllerResponse.success(
                        f"Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y}) in {duration_ms}ms."
                    )
                except ImportError:
                    return ControllerResponse.error("Drag-drop requires Quartz/pyobjc components.")

            elif action == "dump_ui":
                try:
                    raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
                    if not raw_tree or "Error" in raw_tree:
                        return ControllerResponse.error(f"Failed to dump Accessibility Tree: {raw_tree}")
                    elements = await _async_literal_eval(raw_tree.replace("missing value", "None"))
                    if not isinstance(elements, list):
                        return ControllerResponse.error("AX Tree format unexpected.")

                    filtered_elements = elements
                    if max_depth is not None:
                        def _truncate_depth(nodes, depth=0):
                            if depth >= max_depth:
                                return [{k: v for k, v in n.items() if k != "children"} for n in nodes]
                            result = []
                            for n in nodes:
                                item = dict(n)
                                if "children" in item:
                                    item["children"] = _truncate_depth(item["children"], depth + 1)
                                result.append(item)
                            return result
                        filtered_elements = _truncate_depth(elements)
                    if role_filter:
                        filtered_elements = [el for el in filtered_elements if role_filter.lower() in str(el.get("role", "")).lower()]
                    if name_filter:
                        filtered_elements = [el for el in filtered_elements if name_filter.lower() in str(el.get("name", "")).lower()]

                    try:
                        return "\n\n" + render_template(
                            "core/vision/ocr_results.prompt.j2",
                            platform="macos",
                            elements=[{**el, "bounds": el.get("bounds", [])} for el in filtered_elements[:100]],
                            total_count=len(filtered_elements)
                        )
                    except Exception as e:
                        logger.error(f"Failed to render OCR results template: {e}")
                        return PerceptionsFormatter.ui_elements(filtered_elements, max_items=50)

                except Exception as e:
                    return ControllerResponse.error("dump_ui failed.", details=str(e))

            elif action == "gui_extract":
                filepath = await asyncio.to_thread(macos_driver.screenshot, region=region)
                if not filepath or not os.path.exists(filepath):
                    return ControllerResponse.error("Failed to capture screenshot for GUI extraction.")

                try:
                    router = get_vision_router()
                    provider = await router.get_provider(VisionTask.OCR)
                    if not provider:
                        return ControllerResponse.error("No OCR provider available for desktop GUI extraction.")

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
                return ControllerResponse.error(f"Unknown action '{action}'.")

        except PermissionError as e:
            return ControllerResponse.error(
                "PERMISSION ERROR",
                details=str(e),
                note="Please grant Accessibility access to the terminal/application running this backend."
            )
        except Exception as e:
            logger.error(f"Desktop control error: {e}")
            return ControllerResponse.error("Desktop action failed.", details=str(e))

    @classmethod
    async def verify_ui_state(
        cls,
        expected_element: str | None = None,
        expected_role: str | None = None,
        expected_text: str | None = None,
        timeout_seconds: int = 0,
    ) -> str:
        """Verify if a specific UI element or text is present on the screen using AX Tree.

        When timeout_seconds is 0 (default), performs a single immediate check.
        When timeout_seconds > 0, polls every 500ms until the condition is met or timeout.
        """
        async def _check_once():
            raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
            if not raw_tree or "Error" in raw_tree:
                return (False, False), ControllerResponse.error("Verification Failed: Could not dump AX Tree.", details=str(raw_tree))
            elements = await _async_literal_eval(raw_tree)
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
            return (found_element, found_text), None

        try:
            if timeout_seconds <= 0:
                # Immediate check — preserves the original default behavior
                (found_element, found_text), err = await _check_once()
                if err:
                    return err
                if expected_element and not found_element:
                    return ControllerResponse.error(
                        f"Verification FAILED: Element '{expected_element}'" +
                        (f" (role: {expected_role})" if expected_role else "") +
                        " not found."
                    )
                if expected_text and not found_text:
                    return ControllerResponse.error(f"Verification FAILED: Text '{expected_text}' not found.")
                return ControllerResponse.success("Verification SUCCESS: UI state matches expectations.")

            # Polling mode — only when timeout is explicitly requested
            start = asyncio.get_event_loop().time()
            while True:
                (found_element, found_text), err = await _check_once()
                if err:
                    return err
                if (not expected_element or found_element) and (not expected_text or found_text):
                    return ControllerResponse.success("Verification SUCCESS: UI state matches expectations.")
                if asyncio.get_event_loop().time() - start >= timeout_seconds:
                    if expected_element and not found_element:
                        return ControllerResponse.error(
                            f"Verification FAILED: Element '{expected_element}'" +
                            (f" (role: {expected_role})" if expected_role else "") +
                            " not found."
                        )
                    if expected_text and not found_text:
                        return ControllerResponse.error(f"Verification FAILED: Text '{expected_text}' not found.")
                await asyncio.sleep(0.5)
        except Exception as e:
            return ControllerResponse.error("Verification Error.", details=str(e))

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
                    elements = await _async_literal_eval(raw_tree.replace("missing value", "None"))
                except Exception:
                    await asyncio.sleep(0.5)
                    continue
                if check_type == "is_loaded":
                    if len(elements) > 3:
                        elapsed = time.time() - start_time
                        return ControllerResponse.success(
                            f"Screen appears loaded ({len(elements)} elements)",
                            details=f"Elapsed: {elapsed:.2f}s"
                        )
                elif check_type == "has_text" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if target_lower in str(el.get("name", "")).lower() or target_lower in str(el.get("value", "")).lower():
                            return ControllerResponse.success(
                                f"Found text '{target}' on screen",
                                details=f"Elapsed: {time.time() - start_time:.2f}s"
                            )
                elif check_type == "has_element" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if target_lower in str(el.get("name", "")).lower():
                            bounds = el.get("bounds", [])
                            if len(bounds) == 4:
                                ex, ey = int(bounds[0] + bounds[2] / 2), int(bounds[1] + bounds[3] / 2)
                                return ControllerResponse.success(
                                    f"Found element '{target}' at ({ex}, {ey})",
                                    details=f"Elapsed: {time.time() - start_time:.2f}s"
                                )
                            return ControllerResponse.success(
                                f"Found element '{target}'",
                                details=f"Elapsed: {time.time() - start_time:.2f}s"
                            )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"[QuickCheck] Error: {e}")
                await asyncio.sleep(0.5)
        elapsed = time.time() - start_time
        if check_type == "is_loaded":
            return ControllerResponse.error(f"Screen may not be fully loaded after {elapsed:.1f}s")
        return ControllerResponse.error(f"Did not find '{target}' after {elapsed:.1f}s")
