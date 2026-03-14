"""
Mobile Controller — Core Android device automation via ADB.

Extracted from app.domain.tools.environment.mobile to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/mobile.py thin wrapper).
"""
import asyncio
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional

from app.constants import INTERCEPT_TARGETS, RISK_KEYWORDS
from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp
from app.core.context import ContextManager
from app.core.vision import vision_engine, VisionTask
from app.core.vision.providers.native.android_a11y import android_a11y_provider
from app.infrastructure.drivers.adb import ADBError, adb_driver
# REMOVED: from app.core.learning.trace_recorder import get_recorder - Moved to cloud
from app.core.environment.controllers.utils import (
    cleanup_file,
    normalize_text,
    RecordingContext,
    resolve_element_alias,
)

logger = logging.getLogger(__name__)


class MobileController:
    """
    Core Android device automation logic via ADB.

    All methods are classmethods (stateless) — device state lives in the
    singleton `adb_driver` from infrastructure. The Reactor (resolve_element)
    and all Phase 4/5/6 logic are encapsulated here.
    """

    # Package name cache: {device_id: (package_name, timestamp)}
    # Used to avoid repeated ADB queries within a single operation (500ms TTL)
    _package_cache: Dict[str, tuple[str, float]] = {}
    _package_cache_ttl_ms: float = 500.0

    @classmethod
    def _get_cached_package(cls, device_id: str | None) -> str | None:
        """
        Get cached package name if valid (within TTL).

        Args:
            device_id: Device identifier

        Returns:
            Cached package name or None if expired/missing
        """
        if not device_id:
            return None
        cache_entry = cls._package_cache.get(device_id)
        if cache_entry:
            package, timestamp = cache_entry
            elapsed_ms = (time.time() - timestamp) * 1000
            if elapsed_ms < cls._package_cache_ttl_ms:
                logger.debug(f"[MobileController] Using cached package '{package}' for {device_id}")
                return package
        return None

    @classmethod
    def _set_cached_package(cls, device_id: str | None, package: str) -> None:
        """
        Cache package name for device.

        Args:
            device_id: Device identifier
            package: Package name to cache
        """
        if device_id:
            cls._package_cache[device_id] = (package, time.time())

    @classmethod
    async def get_current_app_cached(cls, device_id: str | None = None) -> Dict[str, Any]:
        """
        Get current app with caching support.

        Checks cache first, only queries ADB if cache miss or expired.
        Cache TTL: 500ms to avoid repeated queries within single operation.

        Args:
            device_id: Device identifier

        Returns:
            Dict with 'package', 'activity', 'confidence' keys
        """
        # Check cache first
        cached = cls._get_cached_package(device_id)
        if cached:
            return {"package": cached, "activity": "", "confidence": 1.0}

        # Cache miss - query ADB
        result = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)

        # Update cache if we got a valid package
        if result.get("package") and result["package"] not in ("unknown", "error", ""):
            cls._set_cached_package(device_id, result["package"])

        return result

    @classmethod
    async def execute(
        cls,
        action: str,
        x: int | None = None,
        y: int | None = None,
        x2: int | None = None,
        y2: int | None = None,
        element_name: str | None = None,
        target: str | None = None,
        element_role: str | None = None,
        text: str | None = None,
        keycode: int | str | None = None,
        device_id: str | None = None,
        local_path: str | None = None,
        remote_path: str | None = None,
        duration_ms: int = 300,
        wait_after_ms: int = 0,
        ocr: bool = False,
        timeout: float = 8.0,
        intents: list[dict] | None = None,
        direction: str | None = None,
        scroll_amount: str = "medium",
        after_timestamp: int | None = None,
        region: str | None = None,
        disable_ocr: bool = False,
        **kwargs: Any
    ) -> str:
        """Execute a mobile action. All business logic lives here."""
        # Resolve device_id from context if not provided
        if not device_id:
            device_id = ContextManager.get_var("device_id")
            if device_id:
                logger.debug(f"[Mobile] Using context-bound device: {device_id}")

        session_id = ContextManager.get_var("thread_id")
        recorder = get_recorder(session_id) if session_id else None
        recording_ctx = RecordingContext(
            platform="android",
            recorder=recorder,
            screenshot_actions=("click", "long_press", "swipe", "scroll", "input_text", "open_app"),
            disable_screenshot=kwargs.get("disable_trace_screenshot", False)
        )

        async def _record(action_type: str, params: dict):
            async def screenshot_fn():
                return await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)

            def context_fn():
                # Use cached package if available (sync path - recording context)
                pkg = cls._get_cached_package(device_id)
                if pkg:
                    return {"package": pkg, "activity": ""}
                curr = adb_driver.get_current_app(device_id=device_id)
                return {"package": curr.get("package"), "activity": curr.get("activity")}

            await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

        try:
            # Parameter alias
            element_name = resolve_element_alias(target, element_name)

            # ── Internal helpers (closures capturing context) ──────────────

            async def finish_action(msg: str) -> str:
                """Phase 4/6: wait_after_ms logic."""
                if wait_after_ms > 0:
                    await asyncio.sleep(wait_after_ms / 1000.0)
                    return f"{msg} (waited {wait_after_ms}ms)"
                return msg

            async def probe_hybrid(a11y_result=None) -> bool:
                """Four-Dimensional H5 Detection."""
                if a11y_result is None:
                    a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
                has_webview = False
                if a11y_result.success:
                    has_webview = any("webview" in el.metadata.get("class", "").lower() for el in a11y_result.elements)
                try:
                    curr = await cls.get_current_app_cached(device_id=device_id)
                    act = curr.get("activity", "").lower()
                    hb = any(k in act for k in ["web", "hybrid", "browser", "h5"])
                except Exception:
                    hb = False
                node_count = len(a11y_result.elements) if a11y_result.success and a11y_result.elements else 0
                is_h5 = has_webview or hb or (0 < node_count < 10)
                if is_h5:
                    logger.info(f"[Mobile] Hybrid/H5 detected (Nodes: {node_count})")
                return is_h5

            async def flash_intercept(a11y_result=None) -> bool:
                """Phase 4: Atomic Interceptor - Flash-scan for common close buttons."""
                if a11y_result is None:
                    a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
                if a11y_result.success and a11y_result.elements:
                    for el in a11y_result.elements:
                        txt = normalize_text(el.text)
                        if any(normalize_text(k) in txt for k in INTERCEPT_TARGETS):
                            logger.info(f"[Reactor] Intercepted artifact: '{el.text}' at ({el.x}, {el.y})")
                            await asyncio.to_thread(adb_driver.tap, el.x, el.y, device_id=device_id)
                            await asyncio.sleep(0.5)
                            return True
                return False

            async def check_sentinel(expected_pkg: str | None) -> bool:
                """Phase 4: Activity Sentinel - Detect drift and recover."""
                if not expected_pkg or expected_pkg in ["unknown", "error", "com.android.systemui"]:
                    return True
                status = await asyncio.to_thread(adb_driver.check_app_status, expected_pkg, device_id=device_id)
                if status == "crashed":
                    logger.error(f"[Sentinel] CRASH DETECTED for {expected_pkg}!")
                    await asyncio.to_thread(adb_driver.launch_app, expected_pkg, device_id=device_id)
                    await asyncio.sleep(2.0)
                    return False
                curr = await cls.get_current_app_cached(device_id=device_id)
                curr_pkg = curr.get("package")
                if curr_pkg != expected_pkg and curr_pkg != "com.android.systemui":
                    logger.warning(f"[Sentinel] Drift! Current: {curr_pkg}, Expected: {expected_pkg}. Recovering...")
                    await asyncio.to_thread(adb_driver.press_key, "back", device_id=device_id)
                    await asyncio.sleep(1.2)
                    curr = await cls.get_current_app_cached(device_id=device_id)
                    if curr.get("package") != expected_pkg:
                        await asyncio.to_thread(adb_driver.launch_app, expected_pkg, device_id=device_id)
                        await asyncio.sleep(2.5)
                    return False
                return True

            # Check if Atlas harvesting should be disabled (e.g., during macro execution)
            disable_atlas = kwargs.get("disable_atlas", False)

            async def trigger_atlas_harvest(screenshot_path: str | None = None, bundle_id: str | None = None):
                """Phase 5: Automated Harvesting."""
                if disable_atlas:
                    return  # Skip Atlas harvesting for performance during macro execution
                try:
                    from app.core.atlas.tasks import map_observed_ui_task
                    src = screenshot_path or await asyncio.to_thread(
                        adb_driver.screenshot, device_id=device_id, purpose="atlas", bundle_id=bundle_id
                    )
                    map_observed_ui_task.delay(image_source=src, device_id=device_id, platform="android", bundle_id=bundle_id)
                except Exception as e:
                    logger.warning(f"[Harvest] Failed to trigger: {e}")

            async def check_risk_confirmation(name: str | None = None, input_val: str | None = None) -> str | None:
                """Phase 6: Interactive Safety Guard."""
                for t in [t for t in [name, input_val] if t]:
                    if any(kw.lower() in t.lower() for kw in RISK_KEYWORDS):
                        return f"ERR_CONFIRMATION_REQUIRED: The action involves sensitive operations ('{t}'). Please ask the user to confirm before proceeding with this specific step."
                return None

            async def _normalize_coordinates(
                px: int | float | None,
                py: int | float | None
            ) -> tuple[int | None, int | None]:
                """Convert relative coordinates (0.0-1.0) to pixel coordinates."""
                if px is None or py is None:
                    return px, py
                if not any(isinstance(v, float) for v in [px, py]):
                    return int(px), int(py)
                sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                nx = int(px * sw) if isinstance(px, float) else int(px)
                ny = int(py * sh) if isinstance(py, float) else int(py)
                return nx, ny

            async def _get_current_package() -> str | None:
                """Get current app package name."""
                curr = await cls.get_current_app_cached(device_id=device_id)
                pkg = curr.get("package")
                return None if pkg in ("com.android.launcher3",) else pkg

            async def _resolve_with_fallback(
                name: str,
                role: str | None,
                fallback_x: int | None,
                fallback_y: int | None,
                timeout_val: float = 8.0,
                expected_pkg: str | None = None
            ) -> tuple[int, int] | str:
                """Resolve element with coordinate fallback."""
                resolved = await resolve_element(name, role, timeout_val=timeout_val, expected_pkg=expected_pkg)
                if isinstance(resolved, str):
                    if fallback_x is not None and fallback_y is not None:
                        return fallback_x, fallback_y
                    return resolved
                return resolved["x"], resolved["y"]

            async def _post_action_cleanup(
                action_type: str,
                params: dict,
                package: str | None,
                message: str
            ) -> str:
                """Common cleanup: record, trigger atlas harvest, finish."""
                await _record(action_type, params)
                if package:
                    asyncio.create_task(trigger_atlas_harvest(bundle_id=package))
                return await finish_action(message)

            async def validate_outcome(before_pkg: str, expected_pkg: str | None = None) -> bool:
                """Phase 4: Post-Action Validation."""
                await asyncio.sleep(0.8)
                curr = await cls.get_current_app_cached(device_id=device_id)
                curr_pkg = curr.get("package")
                if curr_pkg != before_pkg and expected_pkg and curr_pkg != expected_pkg:
                    logger.warning(f"[Validation] Drift suspected: {before_pkg} -> {curr_pkg}")
                    return False
                return True

            async def resolve_element(name: str, role: str | None = None, timeout_val: float = 8.0, expected_pkg: str | None = None) -> dict | str:
                """Reactor: High-frequency poll for element with fallback."""
                start_time = time.time()
                target_norm = normalize_text(name)

                # Fetch A11y ONCE per resolve_element start
                initial_a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)

                await flash_intercept(initial_a11y_result)
                is_h5 = await probe_hybrid(initial_a11y_result)

                retry_delay = 0.2
                ocr_attempts = 0
                max_ocr_attempts = 0 if disable_ocr else 2  # Disable OCR if flag is set
                last_sentinel_check = start_time
                used_initial_a11y = False

                while time.time() - start_time < timeout_val:
                    loop_start = time.time()
                    if expected_pkg and (loop_start - last_sentinel_check >= 1.0):
                        await check_sentinel(expected_pkg)
                        last_sentinel_check = loop_start

                    # 1. A11y (Native)
                    if not used_initial_a11y:
                        a11y_result = initial_a11y_result
                        used_initial_a11y = True
                    else:
                        a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
                        
                    if a11y_result.success and a11y_result.elements:
                        candidates = []
                        for el in a11y_result.elements:
                            el_text = normalize_text(el.text)
                            el_res_id = normalize_text(el.metadata.get("resource_id", ""))
                            el_class = str(el.metadata.get("class", "")).lower()
                            score = 0
                            if target_norm == el_text:
                                score = 100
                            elif target_norm in el_text:
                                score = 50
                            elif target_norm in el_res_id:
                                score = 30
                            if score > 0:
                                if role and role.lower() in el_class:
                                    score += 20
                                candidates.append((score, el))
                        if candidates:
                            candidates.sort(key=lambda x: x[0], reverse=True)
                            best_el = candidates[0][1]
                            return {"x": best_el.x, "y": best_el.y}

                    # 2. Atlas Fallback (after 1.5s)
                    elapsed = time.time() - start_time
                    if elapsed > 1.5:
                        try:
                            curr_app = await cls.get_current_app_cached(device_id=device_id)
                            bundle_id = curr_app.get("package")
                            if bundle_id:
                                is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, "android")
                                if is_dynamic:
                                    strategy = await atlas_engine.get_app_strategy(bundle_id, "android")
                                    if strategy:
                                        infra_elem = strategy.get_infrastructure_element(name)
                                        if infra_elem and infra_elem.get("bounds"):
                                            bounds = infra_elem["bounds"]
                                            return {"x": bounds.get("x", 0), "y": bounds.get("y", 0)}
                                        strat = strategy.get_strategy_for(name)
                                        if strat:
                                            return {"strategy": strat.strategy_type, "parameters": strat.parameters, "source": "atlas_strategy"}
                                else:
                                    summary = await atlas_engine.store.get_app_summary(bundle_id, platform="android")
                                    stored_hash = summary.get("version_hash", "")
                                    is_stale = False
                                    if stored_hash:
                                        try:
                                            pkg_meta = await asyncio.to_thread(adb_driver.get_package_info, bundle_id, device_id=device_id)
                                            dummy = AtlasApp(app_name=bundle_id, bundle_id=bundle_id, platform="android")
                                            live_hash = dummy.compute_version_hash(str(pkg_meta.get("version_name", "0")), str(pkg_meta.get("last_update_time", "0")))
                                            if live_hash != stored_hash:
                                                is_stale = True
                                        except Exception:
                                            pass
                                    if not is_stale and summary and "states" in summary:
                                        for state in summary["states"][:3]:
                                            detail = await atlas_engine.store.get_state_detail(bundle_id, state["id"], platform="android")
                                            for el in detail.get("elements", []):
                                                if name.lower() in str(el.get("label", "")).lower():
                                                    return {"x": el["x"], "y": el["y"]}
                        except Exception:
                            pass

                    # 3. OCR Fallback
                    can_ocr = (is_h5 or elapsed > 3.0) and ocr_attempts < max_ocr_attempts
                    if can_ocr:
                        ocr_attempts += 1
                        try:
                            temp_img = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
                            ocr_result = await vision_engine.process(VisionTask.OCR, temp_img, on_android=True, device_id=device_id)
                            if os.path.exists(temp_img):
                                os.remove(temp_img)
                            if ocr_result.success:
                                for el in ocr_result.elements:
                                    if target_norm in normalize_text(el.text):
                                        return {"x": el.x, "y": el.y}
                        except Exception as e:
                            logger.debug(f"[Mobile] OCR attempt {ocr_attempts} failed: {e}")

                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 1.0)

                return f"ERR_ELEMENT_NOT_FOUND: Could not find element '{name}' on device."

            # ── Action dispatch ─────────────────────────────────────────────

            if action == "list_devices":
                devices = await asyncio.to_thread(adb_driver.list_devices)
                if not devices:
                    return "No Android devices connected.\n\nTo connect a device:\n1. Enable Developer Options on your Android device\n2. Enable USB Debugging\n3. Connect via USB and accept the prompt"
                lines = ["Connected devices:"]
                for d in devices:
                    status_emoji = "✅" if d["status"] == "device" else "⚠️"
                    lines.append(f"  {status_emoji} {d['serial']} ({d['status']}) {d['info']}")
                return await finish_action("\n".join(lines))

            elif action == "screenshot":
                filepath = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
                
                # [Phase 15] Handle Region Cropping (Align with Desktop)
                if region and filepath and os.path.exists(filepath):
                    try:
                        from PIL import Image
                        # Expected format: "x,y,w,h"
                        coords = [int(c.strip()) for c in region.split(",")]
                        if len(coords) == 4:
                            rx, ry, rw, rh = coords
                            with Image.open(filepath) as img:
                                # Ensure we don't exceed image bounds
                                img_w, img_h = img.size
                                box = (
                                    max(0, rx), 
                                    max(0, ry), 
                                    min(img_w, rx + rw), 
                                    min(img_h, ry + rh)
                                )
                                cropped = img.crop(box)
                                cropped.save(filepath)
                                logger.info(f"[Mobile] Screenshot cropped to region: {region}")
                    except Exception as e:
                        logger.warning(f"[Mobile] Region cropping failed: {e}")

                msg = f"Screenshot: {filepath}"
                if ocr:
                    try:
                        ocr_res = await vision_engine.process(VisionTask.OCR, filepath, on_android=True, device_id=device_id)
                        if ocr_res.success and ocr_res.elements:
                            msg += "\n\n### OCR Results (Detected Text & Coordinates):\n" + "\n".join([el.to_prompt_line() for el in ocr_res.elements])
                        else:
                            msg += "\n\n(OCR requested but no text detected)"
                    except Exception as e:
                        msg += f"\n\n(OCR Error: {e})"
                return await finish_action(msg)

            elif action in ["tap", "click"]:
                if risk_error := await check_risk_confirmation(name=element_name):
                    return risk_error
                base_pkg = await _get_current_package()
                tx, ty = await _normalize_coordinates(x, y)
                if element_name:
                    result = await _resolve_with_fallback(element_name, element_role, tx, ty, timeout, base_pkg)
                    if isinstance(result, str):
                        return result
                    tx, ty = result
                if tx is None or ty is None:
                    return "Error: Coordinates or element_name required."
                await asyncio.to_thread(adb_driver.tap, tx, ty, device_id=device_id)
                return await _post_action_cleanup(
                    "click",
                    {"x": tx, "y": ty, "element_name": element_name},
                    base_pkg,
                    f"Tapped at ({tx}, {ty})" + (f" (resolved from '{element_name}')" if element_name else "")
                )

            elif action == "long_press":
                if risk_error := await check_risk_confirmation(name=element_name):
                    return risk_error
                base_pkg = await _get_current_package()
                tx, ty = await _normalize_coordinates(x, y)
                if element_name:
                    result = await _resolve_with_fallback(element_name, element_role, tx, ty, timeout, base_pkg)
                    if isinstance(result, str):
                        return result
                    tx, ty = result
                if tx is None or ty is None:
                    return "Error: Coordinates or element_name required."
                press_duration = duration_ms if duration_ms > 300 else 800
                await asyncio.to_thread(adb_driver.long_press, tx, ty, duration_ms=press_duration, device_id=device_id)
                return await _post_action_cleanup(
                    "long_press",
                    {"x": tx, "y": ty, "element_name": element_name, "duration": press_duration},
                    base_pkg,
                    f"Long-pressed at ({tx}, {ty}) for {press_duration}ms" + (f" (resolved from '{element_name}')" if element_name else "")
                )

            elif action == "swipe":
                if risk_error := await check_risk_confirmation(name=element_name):
                    return risk_error
                if any(v is None for v in [x, y, x2, y2]):
                    return "Error: Need x, y, x2, y2."
                rx, ry = await _normalize_coordinates(x, y)
                rx2, ry2 = await _normalize_coordinates(x2, y2)
                await asyncio.to_thread(adb_driver.swipe, rx, ry, rx2, ry2, duration_ms=duration_ms, device_id=device_id)
                base_pkg = await _get_current_package()
                return await _post_action_cleanup(
                    "swipe",
                    {"x1": rx, "y1": ry, "x2": rx2, "y2": ry2, "duration": duration_ms},
                    base_pkg,
                    f"Swiped from ({rx}, {ry}) to ({rx2}, {ry2})"
                )

            elif action == "scroll":
                if not direction:
                    return "Error: 'direction' (up/down/left/right) is required for scroll."
                sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                if isinstance(scroll_amount, (int, float)):
                    scroll_ratio = min(1.0, max(0.1, float(scroll_amount)))
                else:
                    amount_map = {"small": 0.3, "medium": 0.5, "large": 0.7, "full": 0.9}
                    scroll_ratio = amount_map.get(scroll_amount, 0.5)

                scroll_distance = int(sh * scroll_ratio) if direction in ("up", "down") else int(sw * scroll_ratio)
                center_x = int(sw * 0.5)
                center_y = int(sh * 0.5)
                if element_name:
                    resolved = await resolve_element(element_name, element_role, timeout_val=timeout)
                    if isinstance(resolved, str):
                        return resolved
                    center_x, center_y = resolved.get("x", center_x), resolved.get("y", center_y)

                # Calculate swipe coordinates based on direction
                if direction == "up":
                    start_x = end_x = center_x
                    start_y, end_y = center_y - scroll_distance // 2, center_y + scroll_distance // 2
                elif direction == "down":
                    start_x = end_x = center_x
                    start_y, end_y = center_y + scroll_distance // 2, center_y - scroll_distance // 2
                elif direction == "left":
                    start_y = end_y = center_y
                    start_x, end_x = center_x - scroll_distance // 2, center_x + scroll_distance // 2
                else:  # right
                    start_y = end_y = center_y
                    start_x, end_x = center_x + scroll_distance // 2, center_x - scroll_distance // 2

                start_x, start_y = max(0, min(sw, start_x)), max(0, min(sh, start_y))
                end_x, end_y = max(0, min(sw, end_x)), max(0, min(sh, end_y))

                await asyncio.to_thread(adb_driver.swipe, start_x, start_y, end_x, end_y, duration_ms=duration_ms, device_id=device_id)
                base_pkg = await _get_current_package()
                return await _post_action_cleanup(
                    "scroll",
                    {"direction": direction, "amount": scroll_amount, "element_name": element_name},
                    base_pkg,
                    f"Scrolled {direction} by {scroll_amount}" + (f" (in '{element_name}')" if element_name else "")
                )

            elif action == "input_text":
                if not text:
                    return "Error: 'text' required."
                if risk_error := await check_risk_confirmation(name=element_name, input_val=text):
                    return risk_error
                base_pkg = await _get_current_package()
                if element_name:
                    resolved = await resolve_element(element_name, element_role, timeout_val=timeout, expected_pkg=base_pkg)
                    if isinstance(resolved, str):
                        return resolved
                    await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                    await asyncio.sleep(0.5)
                await asyncio.to_thread(adb_driver.input_text, text, device_id=device_id)
                return await _post_action_cleanup(
                    "input_text",
                    {"text": text, "element_name": element_name},
                    base_pkg,
                    f"Input text: {text[:50]}..." + (f" (focused on '{element_name}')" if element_name else "")
                )

            elif action == "scroll_to_bottom":
                # [Phase 20] Incremental Scrolling for Infinite lists
                max_scrolls = int(kwargs.get("max_scrolls", 5))
                scroll_amount = kwargs.get("scroll_amount", "medium")
                delay_ms = int(kwargs.get("delay_ms", 1000))
                
                # Mapping distance
                size = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                width, height = size
                
                start_x = width // 2
                end_x = start_x
                
                if scroll_amount == "small":
                    distance = height // 4
                elif scroll_amount == "large":
                    distance = (height // 4) * 3
                else: # medium
                    distance = height // 2
                
                start_y = (height // 2) + (distance // 2)
                end_y = (height // 2) - (distance // 2)
                
                scroll_count = 0
                last_ui_hash = ""
                
                while scroll_count < max_scrolls:
                    # 1. Capture current state for stability check
                    try:
                        curr_ui = await asyncio.to_thread(adb_driver.dump_ui, device_id=device_id)
                        curr_hash = str(hash(curr_ui))
                    except:
                        curr_hash = str(time.time()) # Fallback if dump fails
                    
                    if curr_hash == last_ui_hash:
                        logger.info(f"[Mobile] Scroll reached bottom (UI stable) after {scroll_count} scrolls.")
                        break
                    
                    last_ui_hash = curr_hash
                    
                    # 2. Perform Swipe
                    await asyncio.to_thread(adb_driver.swipe, start_x, start_y, end_x, end_y, duration_ms=400, device_id=device_id)
                    scroll_count += 1
                    await asyncio.sleep(delay_ms / 1000.0)
                
                return await finish_action(f"Scrolled {scroll_count} times.")

            elif action == "press_key":
                if keycode is None:
                    return "Error: 'keycode' required."
                await asyncio.to_thread(adb_driver.press_key, keycode, device_id=device_id)
                return await finish_action(f"Pressed: {keycode}")

            elif action == "get_info":
                info = await asyncio.to_thread(adb_driver.get_system_info, device_id=device_id)
                return await finish_action(str(info))

            elif action == "list_apps":
                apps = await asyncio.to_thread(adb_driver.list_installed_apps, device_id=device_id)
                return await finish_action(str(apps))

            elif action == "open_app":
                if not text:
                    return "Error: package name in 'text' required."

                # Check for force_stop flag (useful for clean macro starts)
                if kwargs.get("force_stop") or kwargs.get("restart", False):
                    await asyncio.to_thread(adb_driver.force_stop, text, device_id=device_id)
                    await asyncio.sleep(0.5)

                is_dynamic = await atlas_engine.is_dynamic_app(text, "android")
                icon = "🔄" if is_dynamic else "📍"
                app_type_str = "DYNAMIC" if is_dynamic else "STATIC"

                # Launch app first
                await asyncio.to_thread(adb_driver.launch_app, text, device_id=device_id)

                # Preload Atlas data in background for faster subsequent operations
                async def _preload_atlas_data():
                    """Background task to preload Atlas data after app launch."""
                    try:
                        if is_dynamic:
                            # For dynamic apps: preload strategy
                            strategy = await atlas_engine.get_app_strategy(text, "android")
                            if strategy:
                                logger.info(f"[Mobile] Atlas strategy preloaded for {text}")
                        else:
                            # For static apps: trigger harvest
                            await trigger_atlas_harvest(bundle_id=text)
                    except Exception as e:
                        logger.debug(f"[Mobile] Atlas preload for {text} (non-critical): {e}")

                asyncio.create_task(_preload_atlas_data())

                await _record("open_app", {"package": text, "type": app_type_str})
                return await finish_action(f"{icon} Opened: {text} [{app_type_str}]")

            elif action == "push":
                if not local_path or not remote_path:
                    return "Error: 'local_path' and 'remote_path' are required for push."
                await asyncio.to_thread(adb_driver.push, local_path, remote_path, device_id=device_id)
                return await finish_action("Pushed")

            elif action == "pull":
                if not local_path or not remote_path:
                    return "Error: 'local_path' and 'remote_path' are required for pull."
                await asyncio.to_thread(adb_driver.pull, remote_path, local_path, device_id=device_id)
                return await finish_action("Pulled")

            elif action == "dump_ui":
                xml = await asyncio.to_thread(adb_driver.dump_ui, device_id=device_id)
                if len(xml) > 200000:
                    xml = xml[:200000] + "\n...(truncated)"
                return await finish_action(f"UI Hierarchy:\n{xml}")

            elif action == "intent_flow":
                if not intents:
                    return "Error: 'intents' list is required for intent_flow."
                steps_done = 0
                base_pkg = await _get_current_package()

                async def _execute_intent_step(it: dict) -> str | None:
                    """Execute a single intent step. Returns error message or None on success."""
                    act = it.get("action")
                    tgt = it.get("target") or it.get("element_name")
                    if risk_error := await check_risk_confirmation(name=tgt, input_val=it.get("text")):
                        return risk_error

                    if act == "click" and tgt:
                        resolved = await resolve_element(tgt, expected_pkg=base_pkg, timeout_val=timeout)
                        if isinstance(resolved, str):
                            return resolved
                        await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                        if not await validate_outcome(base_pkg):
                            await check_sentinel(base_pkg)
                    elif act == "input" and it.get("text"):
                        if tgt:
                            resolved = await resolve_element(tgt, expected_pkg=base_pkg, timeout_val=timeout)
                            if isinstance(resolved, str):
                                return resolved
                            await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                            await asyncio.sleep(0.3)
                        await asyncio.to_thread(adb_driver.input_text, it["text"], device_id=device_id)
                    return None

                for it in intents:
                    if error := await _execute_intent_step(it):
                        return error
                    steps_done += 1
                    await asyncio.sleep(0.5)

                asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
                return await finish_action(f"Successfully executed intent flow with {steps_done} steps.")

            elif action == "read_sms":
                pattern = text if text else r'\d{4,6}'
                wait_time = int(timeout) if timeout else 30
                # after_timestamp allows filtering SMS received after a specific time (milliseconds)
                logger.info(f"Polling SMS inbox for pattern '{pattern}' up to {wait_time}s..." + (f" (after timestamp: {after_timestamp})" if after_timestamp else ""))
                messages = await asyncio.to_thread(adb_driver.read_sms, regex_pattern=pattern, timeout=wait_time, device_id=device_id, after_timestamp=after_timestamp)
                if not messages:
                    return await finish_action(f"No SMS matching pattern '{pattern}' received within {wait_time} seconds.")
                latest = messages[0]
                if latest.get("extract"):
                    return await finish_action(f"SMS Received! Extracted Match: {latest['extract']}\nFull Body: {latest['body']}")
                return await finish_action(f"SMS Received: {latest['body']}")

            elif action == "get_clipboard":
                text = await asyncio.to_thread(adb_driver.get_clipboard, device_id=device_id)
                return await finish_action(text or "")

            elif action == "gui_extract":
                from app.core.vision import get_vision_router

                def _crop_screenshot(filepath: str, region_str: str) -> bool:
                    try:
                        from PIL import Image
                        coords = [int(c.strip()) for c in region_str.split(",")]
                        if len(coords) != 4:
                            return False
                        rx, ry, rw, rh = coords
                        with Image.open(filepath) as img:
                            box = (max(0, rx), max(0, ry), min(img.size[0], rx + rw), min(img.size[1], ry + rh))
                            img.crop(box).save(filepath)
                        return True
                    except Exception:
                        return False

                def _group_elements_to_rows(elements, screen_height: int = 2400):
                    threshold = screen_height * 0.05
                    sorted_elements = sorted(elements, key=lambda e: e.y)
                    rows, current_row, last_y = [], [], -float('inf')

                    for el in sorted_elements:
                        if abs(el.y - last_y) > threshold:
                            if current_row:
                                avg_x = sum(e.x for e in current_row) / len(current_row)
                                avg_y = sum(e.y for e in current_row) / len(current_row)
                                rows.append({
                                    "text": " | ".join([e.text for e in sorted(current_row, key=lambda x: x.x)]),
                                    "x": int(avg_x), "y": int(avg_y)
                                })
                            current_row, last_y = [el], el.y
                        else:
                            current_row.append(el)

                    if current_row:
                        avg_x = sum(e.x for e in current_row) / len(current_row)
                        avg_y = sum(e.y for e in current_row) / len(current_row)
                        rows.append({
                            "text": " | ".join([e.text for e in sorted(current_row, key=lambda x: x.x)]),
                            "x": int(avg_x), "y": int(avg_y)
                        })
                    return rows

                # 1. Capture Screenshot
                filepath = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
                if region and filepath:
                    _crop_screenshot(filepath, region)

                if not filepath or not os.path.exists(filepath):
                    return "Error: Failed to capture screenshot for GUI extraction."

                try:
                    router = get_vision_router()
                    provider = await router.get_provider(VisionTask.OCR, on_android=True, device_id=device_id)
                    if not provider:
                        return "Error: No OCR provider available for mobile GUI extraction."

                    result = await provider.process(VisionTask.OCR, filepath)
                    if not result.success or not result.elements:
                        return "[]" if kwargs.get("extraction_method") == "list" or "loop" in str(kwargs) else ""

                    is_list_request = kwargs.get("extraction_method") in ("list", "ocr_region")

                    if is_list_request:
                        _, screen_height = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                        rows = _group_elements_to_rows(result.elements, screen_height)
                        return json.dumps(rows, ensure_ascii=False) if kwargs.get("extraction_method") == "list" else rows

                    # Standard Nearby Matching (Single Item)
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

            return f"Error: Unknown action '{action}'."

        except ADBError as e:
            return f"⚠️ ADB ERROR: {e}"
        except Exception as e:
            logger.error(f"Mobile control error: {e}")
            return f"Error: {str(e)}"
