"""
Mobile Controller — Core Android device automation via ADB.

Extracted from app.core.environment.tools.mobile to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/mobile.py thin wrapper).
"""

import asyncio
import logging
import os
import time
from functools import partial
from typing import Any

from app.core.atlas import atlas_engine
from app.core.context import ContextManager
from app.core.environment.controllers.utils import (
    RecordingContext,
    resolve_element_alias,
)
from app.core.environment.schemas import AppInfo
from app.core.learning.trace.recorder import get_recorder
from app.infrastructure.drivers.adb import ADBError, adb_driver
from app.infrastructure.vision import VisionTask, vision_engine
from app.infrastructure.vision.providers.native.android_a11y import (
    android_a11y_provider,
)
from app.utils.controller_response import ControllerResponse
from app.utils.text import normalize_text
from app.utils.time import elapsed_ms

from ._advanced import MobileAdvancedMixin
from ._app import MobileAppMixin
from ._interaction import MobileInteractionMixin

logger = logging.getLogger(__name__)


class MobileController(
    MobileInteractionMixin,
    MobileAppMixin,
    MobileAdvancedMixin,
):
    """
    Core Android device automation logic via ADB.

    All methods are classmethods (stateless) — device state lives in the
    singleton `adb_driver` from infrastructure. The Reactor (resolve_element)
    and all Phase 4/5/6 logic are encapsulated here.
    """

    _package_cache: dict[str, tuple[str, float]] = {}
    _package_cache_ttl_ms: float = 500.0

    _screenshot_cache: dict[str, tuple[str, float]] = {}
    _screenshot_cache_ttl_ms: float = 1000.0

    @classmethod
    def _get_cached_package(cls, device_id: str | None) -> str | None:
        if not device_id:
            return None
        cache_entry = cls._package_cache.get(device_id)
        if cache_entry:
            package, timestamp = cache_entry
            e_ms = elapsed_ms(timestamp)
            if e_ms < cls._package_cache_ttl_ms:
                logger.debug(f"[MobileController] Using cached package '{package}' for {device_id}")
                return package
        return None

    @classmethod
    def _set_cached_package(cls, device_id: str | None, package: str) -> None:
        if device_id:
            cls._package_cache[device_id] = (package, time.time())

    @classmethod
    async def get_current_app_cached(cls, device_id: str | None = None) -> AppInfo:
        cached = cls._get_cached_package(device_id)
        if cached:
            return AppInfo(package=cached, activity="", confidence=1.0)

        result = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
        if result.get("package") and result["package"] not in ("unknown", "error", ""):
            cls._set_cached_package(device_id, result["package"])

        return AppInfo.model_validate(result)

    # ── Internal helpers (extracted from `execute` closures) ──────────────
    # Each takes the shared `ctx` dict explicitly instead of capturing it.
    # They are bound into `ctx` via `functools.partial` so mixin handlers
    # can keep calling them through the same `ctx[...]` interface.

    @classmethod
    async def _record(cls, ctx: dict, action_type: str, params: dict) -> None:
        recording_ctx = ctx["recording_ctx"]
        device_id = ctx.get("device_id")
        _get_effective_package = ctx["_get_effective_package"]

        async def screenshot_fn():
            pkg = await _get_effective_package()
            return await asyncio.to_thread(adb_driver.screenshot, device_id=device_id, bundle_id=pkg)

        async def context_fn():
            pkg = await _get_effective_package()
            curr = await cls.get_current_app_cached(device_id=device_id)
            return {"package": pkg, "activity": curr.get("activity")}

        await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

    @classmethod
    async def _finish_action(
        cls,
        ctx: dict,
        msg: str | dict,
        success: bool = True,
        note: str | None = None,
    ) -> str:
        wait_after_ms = ctx.get("wait_after_ms", 0)
        if wait_after_ms > 0:
            await asyncio.sleep(wait_after_ms / 1000.0)

        if isinstance(msg, str):
            from app.utils.template import render_template

            wait_note = f"Wait: {wait_after_ms}ms" if wait_after_ms > 0 else None
            final_note = f"{note} ({wait_note})" if note and wait_note else (note or wait_note)
            return render_template("common/report/response.prompt.j2", success=success, message=msg, note=final_note)
        return str(msg)

    @classmethod
    async def _probe_hybrid(cls, ctx: dict, a11y_result=None) -> bool:
        device_id = ctx.get("device_id")
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

    @classmethod
    async def _check_sentinel(cls, ctx: dict, expected_pkg: str | None) -> bool:
        device_id = ctx.get("device_id")
        passive_safety = ctx.get("passive_safety", False)
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
            if passive_safety:
                logger.info("[Sentinel] Passive Safety enabled: Skipping auto-recovery actions.")
                return False
            await asyncio.to_thread(adb_driver.press_key, "back", device_id=device_id)
            await asyncio.sleep(1.2)
            curr = await cls.get_current_app_cached(device_id=device_id)
            if curr.get("package") != expected_pkg:
                await asyncio.to_thread(adb_driver.launch_app, expected_pkg, device_id=device_id)
                await asyncio.sleep(2.5)
            return False
        return True

    @classmethod
    async def _trigger_atlas_harvest(
        cls,
        ctx: dict,
        screenshot_path: str | None = None,
        bundle_id: str | None = None,
    ) -> None:
        disable_atlas = ctx.get("disable_atlas", False)
        device_id = ctx.get("device_id")
        if disable_atlas:
            return
        logger.debug(
            f"[Harvest] Atlas UI mapping task not implemented (map_observed_ui), "
            f"skip for device={device_id}, screenshot={screenshot_path}"
        )

    @classmethod
    async def _normalize_coordinates(
        cls,
        ctx: dict,
        px: int | float | None,
        py: int | float | None,
    ) -> tuple[int | None, int | None]:
        device_id = ctx.get("device_id")
        if px is None or py is None:
            return px, py
        if not any(isinstance(v, float) for v in [px, py]):
            return int(px), int(py)
        sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
        nx = int(px * sw) if isinstance(px, float) else int(px)
        ny = int(py * sh) if isinstance(py, float) else int(py)
        return nx, ny

    @classmethod
    async def _get_current_package(cls, ctx: dict) -> str | None:
        device_id = ctx.get("device_id")
        curr = await cls.get_current_app_cached(device_id=device_id)
        pkg = curr.get("package")
        return None if pkg in ("com.android.launcher3", "com.android.systemui") else pkg

    @classmethod
    async def _get_effective_package(cls, ctx: dict) -> str | None:
        expected_pkg = ctx.get("expected_pkg")
        detected_pkg = await cls._get_current_package(ctx)

        if not expected_pkg:
            return detected_pkg

        if not detected_pkg or detected_pkg == "unknown":
            return expected_pkg

        NOISY_PACKAGES = {
            "com.tencent.mm",
            "com.android.systemui",
            "com.android.launcher3",
            "com.google.android.inputmethod.latin",
            "android",
        }

        if detected_pkg in NOISY_PACKAGES and detected_pkg != expected_pkg:
            logger.debug(f"[Mobile] Detected noisy package '{detected_pkg}', sticking to expected '{expected_pkg}'")
            return expected_pkg

        if detected_pkg != expected_pkg:
            logger.info(f"[Mobile] Legitimate cross-app switch detected: {expected_pkg} -> {detected_pkg}")

        return detected_pkg

    @classmethod
    async def _resolve_with_fallback(
        cls,
        ctx: dict,
        name: str,
        role: str | None,
        fallback_x: int | None,
        fallback_y: int | None,
        timeout_val: float = 8.0,
        expected_pkg: str | None = None,
        fast_probe_enabled: bool = False,
    ) -> dict | tuple[int, int] | str:
        resolve_element = ctx["resolve_element"]
        resolved = await resolve_element(
            name,
            role,
            timeout_val=timeout_val,
            expected_pkg=expected_pkg,
            fast_probe=fast_probe_enabled,
            has_fallback=(fallback_x is not None and fallback_y is not None),
        )
        if isinstance(resolved, str):
            if fallback_x is not None and fallback_y is not None:
                return fallback_x, fallback_y
            return resolved
        return resolved["x"], resolved["y"]

    @classmethod
    async def _post_action_cleanup(
        cls,
        ctx: dict,
        action_type: str,
        params: dict,
        message: str,
    ) -> str:
        _get_effective_package = ctx["_get_effective_package"]
        _record = ctx["recording_func"]
        disable_atlas = ctx.get("disable_atlas", False)
        trigger_atlas_harvest = ctx["trigger_atlas_harvest"]
        finish_action = ctx["finish_action"]
        effective_pkg = await _get_effective_package()
        await _record(action_type, params)
        if effective_pkg and not disable_atlas:
            asyncio.create_task(trigger_atlas_harvest(bundle_id=effective_pkg))
        return await finish_action(message)

    @classmethod
    async def _validate_outcome(cls, ctx: dict, before_pkg: str, expected_pkg: str | None = None) -> bool:
        device_id = ctx.get("device_id")
        curr = await cls.get_current_app_cached(device_id=device_id)
        curr_pkg = curr.get("package")
        if curr_pkg != before_pkg and expected_pkg and curr_pkg != expected_pkg:
            logger.warning(f"[Validation] Drift suspected: {before_pkg} -> {curr_pkg}")
            return False
        return True

    @classmethod
    async def _resolve_element(
        cls,
        ctx: dict,
        name: str,
        role: str | None = None,
        timeout_val: float = 8.0,
        expected_pkg: str | None = None,
        fast_probe: bool = False,
        has_fallback: bool = False,
    ) -> dict | str:
        from app.utils.template import render_template

        device_id = ctx.get("device_id")
        compressed_dump = ctx.get("compressed_dump", True)
        disable_ocr = ctx.get("disable_ocr", False)
        probe_hybrid = ctx["probe_hybrid"]
        check_sentinel = ctx["check_sentinel"]

        start_time = time.time()
        target_norm = normalize_text(name)

        effective_timeout = timeout_val
        if fast_probe and has_fallback:
            effective_timeout = min(1.5, timeout_val / 4.0)
            logger.info(f"[Reactor] Fast Probe enabled with fallback. Adaptive timeout: {effective_timeout:.2f}s")

        initial_a11y_result = await android_a11y_provider.process(
            VisionTask.DETECT, "", device_id=device_id, compressed=compressed_dump
        )

        is_h5 = await probe_hybrid(initial_a11y_result)

        ocr_attempts = 0
        max_ocr_attempts = 0 if disable_ocr else 2
        last_sentinel_check = start_time
        used_initial_a11y = False

        while time.time() - start_time < effective_timeout:
            loop_start = time.time()
            if expected_pkg and (loop_start - last_sentinel_check >= 1.0):
                await check_sentinel(expected_pkg)
                last_sentinel_check = loop_start

            if not used_initial_a11y:
                a11y_result = initial_a11y_result
                used_initial_a11y = True
            else:
                a11y_result = await android_a11y_provider.process(
                    VisionTask.DETECT,
                    "",
                    device_id=device_id,
                    compressed=compressed_dump,
                )

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

            elapsed = time.time() - start_time
            if elapsed > 1.5:
                curr_app = await cls.get_current_app_cached(device_id=device_id)
                bundle_id = curr_app.get("package")
                if bundle_id:
                    atlas_res = await atlas_engine.resolve_spatial_element(
                        bundle_id, name, platform="android"
                    )
                    if atlas_res:
                        return atlas_res

            can_ocr = (is_h5 or elapsed > 3.0) and ocr_attempts < max_ocr_attempts
            if can_ocr:
                ocr_attempts += 1
                try:
                    temp_img = await asyncio.to_thread(adb_driver.screenshot, device_id=device_id)
                    ocr_result = await vision_engine.process(
                        VisionTask.OCR,
                        temp_img,
                        on_android=True,
                        device_id=device_id,
                        enable_atlas_learning=False,
                    )
                    if os.path.exists(temp_img):
                        os.remove(temp_img)
                    if ocr_result.success:
                        for el in ocr_result.elements:
                            if target_norm in normalize_text(el.text):
                                return {"x": el.x, "y": el.y}
                except Exception as e:
                    logger.debug(f"[Mobile] OCR attempt {ocr_attempts} failed: {e}", exc_info=True)

            await asyncio.sleep(0.05)

        return render_template(
            "common/report/response.prompt.j2",
            success=False,
            message=f"Could not find element '{name}' on device.",
        )

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
        fast_probe: bool = False,
        passive_safety: bool = False,
        compressed_dump: bool = True,
        expected_pkg: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not device_id:
            device_id = ContextManager.get_var("device_id")
            if device_id:
                logger.debug(f"[Mobile] Using context-bound device: {device_id}")

        session_id = ContextManager.get_var("thread_id")
        recorder = get_recorder(session_id) if session_id else None
        recording_ctx = RecordingContext(
            platform="android",
            recorder=recorder,
            screenshot_actions=(
                "click",
                "long_press",
                "swipe",
                "scroll",
                "input_text",
                "open_app",
            ),
            disable_screenshot=kwargs.get("disable_trace_screenshot", False),
        )

        try:
            element_name = resolve_element_alias(target, element_name)

            disable_atlas = kwargs.get("disable_atlas", False)

            # ── Build shared context for mixin handlers ──────────────────
            # Internal helpers are bound as `functools.partial(cls._method, ctx)`
            # so mixin handlers keep using the same `ctx[...]` call interface.
            # Lookups happen at call time, so cross-references between helpers
            # (e.g. `_post_action_cleanup` calling `finish_action`) resolve
            # correctly regardless of insertion order.
            ctx: dict[str, Any] = {
                "recording_ctx": recording_ctx,
                "x": x, "y": y, "x2": x2, "y2": y2,
                "element_name": element_name,
                "element_role": element_role,
                "text": text,
                "keycode": keycode,
                "device_id": device_id,
                "local_path": local_path,
                "remote_path": remote_path,
                "duration_ms": duration_ms,
                "wait_after_ms": wait_after_ms,
                "ocr": ocr,
                "timeout": timeout,
                "intents": intents,
                "direction": direction,
                "scroll_amount": scroll_amount,
                "after_timestamp": after_timestamp,
                "region": region,
                "disable_ocr": disable_ocr,
                "disable_atlas": disable_atlas,
                "fast_probe": fast_probe,
                "passive_safety": passive_safety,
                "compressed_dump": compressed_dump,
                "expected_pkg": expected_pkg,
                "kwargs": kwargs,
            }
            ctx["finish_action"] = partial(cls._finish_action, ctx)
            ctx["probe_hybrid"] = partial(cls._probe_hybrid, ctx)
            ctx["check_sentinel"] = partial(cls._check_sentinel, ctx)
            ctx["trigger_atlas_harvest"] = partial(cls._trigger_atlas_harvest, ctx)
            ctx["_normalize_coordinates"] = partial(cls._normalize_coordinates, ctx)
            ctx["_get_current_package"] = partial(cls._get_current_package, ctx)
            ctx["_get_effective_package"] = partial(cls._get_effective_package, ctx)
            ctx["_resolve_with_fallback"] = partial(cls._resolve_with_fallback, ctx)
            ctx["_post_action_cleanup"] = partial(cls._post_action_cleanup, ctx)
            ctx["validate_outcome"] = partial(cls._validate_outcome, ctx)
            ctx["resolve_element"] = partial(cls._resolve_element, ctx)
            ctx["recording_func"] = partial(cls._record, ctx)

            # ── Dispatch ─────────────────────────────────────────────────
            if action in (
                "tap",
                "click",
                "long_press",
                "swipe",
                "scroll",
                "scroll_to_bottom",
                "input_text",
                "press_key",
            ):
                result = await cls._handle_interaction(action, **ctx)
                if result is not None:
                    return result

            if action in ("get_info", "list_apps", "open_app"):
                result = await cls._handle_app(action, **ctx)
                if result is not None:
                    return result

            if action in (
                "list_devices",
                "screenshot",
                "push",
                "pull",
                "dump_ui",
                "intent_flow",
                "read_sms",
                "get_clipboard",
                "gui_extract",
            ):
                result = await cls._handle_advanced(action, **ctx)
                if result is not None:
                    return result

            return ControllerResponse.error(f"Unknown action '{action}'.")

        except ADBError as e:
            return ControllerResponse.error("ADB ERROR", details=str(e))
        except Exception as e:
            logger.exception(f"Mobile control error: {e}")
            return ControllerResponse.error("Mobile action failed.", details=str(e))
