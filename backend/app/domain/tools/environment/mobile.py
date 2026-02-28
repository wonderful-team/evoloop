"""
Mobile Control Tool - Android device interaction capability via ADB.
Provides the Agent with the ability to see and interact with Android devices.
"""
import os
import asyncio
import logging
import time
from typing import Literal

from app.constants import INTERCEPT_TARGETS, RISK_KEYWORDS
from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp
from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask
from app.core.vision.providers.native.android_a11y import android_a11y_provider
from app.infrastructure.drivers.adb import ADBError, adb_driver

logger = logging.getLogger(__name__)


@evoloop_tool
async def mobile_control(
    action: Literal["screenshot", "tap", "click", "long_press", "swipe", "input_text", "press_key", "dump_ui", "list_devices", "get_info", "list_apps", "open_app", "push", "pull", "intent_flow", "read_sms"],
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
    timeout: float = 8.0,
    intents: list[dict] | None = None,
) -> str:

    """
    Control an Android device via ADB with Local Reactive Loop (Reactor) support.
    
    This tool supports atomic actions and high-speed 'intent flows' for fluid interaction.
    
    Args:
        action: The action to perform:
            - "intent_flow": A sequence of intents (click/input) executed locally with high frequency.
            - "screenshot": Capture the device screen. Returns path to image file.
            - "tap": Tap at coordinates (x, y).
            - "click": Semantic click. Polls locally if element_name is used (Reactor).
            - "long_press": Long-press at (x, y) OR element_name.
            - "swipe": Swipe from (x, y) to (x2, y2).
            - "input_text": Type text. If element_name given, taps it first.
            - "press_key": Press a key (home, back, enter, etc.).
            - "dump_ui": Get UI hierarchy as XML.
            - "list_devices": List connected devices.
            - "list_apps": List installed 3rd-party packages.
            - "open_app": Open app by package name (passed in 'text').
            - "push": Push a local file/directory to the device.
            - "pull": Pull a remote file/directory from the device.
            - "read_sms": Poll device SMS inbox. 'text' = regex pattern. 'timeout' = max wait seconds. Starts polling immediately.
        intents: List of intent dicts for "intent_flow" action. 
                 E.g. [{"action": "click", "target": "Search"}, {"action": "input", "text": "iPhone"}]
        x, y, x2, y2: Coordinates (can be absolute or relative 0.0-1.0).
        element_name: Semantic name/label of the UI element.
        element_role: Optional role/class filter.
        text: Text to input OR package name.
        keycode: Key name or code for press_key.
        local_path: Full path on the host Mac (required for push/pull).
        remote_path: Full path on the Android device (required for push/pull).
        device_id: Optional device serial.
        ocr: Perform OCR on screenshot.
    """
    try:
        import unicodedata
        def normalize_text(t: str) -> str:
            if not t:
                return ""
            return unicodedata.normalize('NFC', str(t)).lower().strip().replace(" ", "").replace("\u3000", "")

        async def probe_hybrid() -> bool:
            """Four-Dimensional H5 Detection."""
            a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
            has_webview = False
            if a11y_result.success:
                has_webview = any("webview" in el.metadata.get("class", "").lower() for el in a11y_result.elements)
            
            # Check activity for H5 markers
            try:
                curr = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                act = curr.get("activity", "").lower()
                hb = any(k in act for k in ["web", "hybrid", "browser", "h5"])
            except:
                hb = False

            node_count = len(a11y_result.elements) if a11y_result.success and a11y_result.elements else 0
            is_h5 = has_webview or hb or (node_count < 10 and node_count > 0)
            if is_h5:
                logger.info(f"[Mobile] Hybrid/H5 detected (Activity: {act}, Nodes: {node_count})")
            return is_h5

        async def flash_intercept():
            """Phase 4: Atomic Interceptor - Flash-scan for common close buttons."""
            a11y_res = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
            if a11y_res.success and a11y_res.elements:
                for el in a11y_res.elements:
                    txt = normalize_text(el.text)
                    if any(normalize_text(k) in txt for k in INTERCEPT_TARGETS):
                        logger.info(f"[Reactor] Intercepted artifact: '{el.text}' at ({el.x}, {el.y})")
                        await asyncio.to_thread(adb_driver.tap, el.x, el.y, device_id=device_id)
                        await asyncio.sleep(0.5)
                        return True
            return False

        async def check_sentinel(expected_pkg: str | None):
            """Phase 4: Activity Sentinel - Detect drift and recover."""
            if not expected_pkg or expected_pkg in ["unknown", "error", "com.android.systemui"]: return True
            
            # Phase 4: Crash detection
            status = await asyncio.to_thread(adb_driver.check_app_status, expected_pkg, device_id=device_id)
            if status == "crashed":
                logger.error(f"[Sentinel] CRASH DETECTED for {expected_pkg}!")
                await asyncio.to_thread(adb_driver.launch_app, expected_pkg, device_id=device_id)
                await asyncio.sleep(2.0)
                return False

            curr = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            curr_pkg = curr.get("package")
            # If we are not in the expected app and not in a system overlay, it's a drift
            if curr_pkg != expected_pkg and curr_pkg != "com.android.systemui":
                logger.warning(f"[Sentinel] Drift detected! Current: {curr_pkg}, Expected: {expected_pkg}. Recovering...")
                # Try Back first
                await asyncio.to_thread(adb_driver.press_key, "back", device_id=device_id)
                await asyncio.sleep(1.2)
                # Re-check
                curr = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                if curr.get("package") != expected_pkg:
                    logger.info(f"[Sentinel] Back failed, force re-launching {expected_pkg}")
                    await asyncio.to_thread(adb_driver.launch_app, expected_pkg, device_id=device_id)
                    await asyncio.sleep(2.5)
                return False
            return True

        async def trigger_atlas_harvest(screenshot_path: str | None = None, bundle_id: str | None = None):
            """Phase 5: Automated Harvesting - Map current UI to App Atlas in background."""
            try:
                from app.core.atlas.tasks import map_observed_ui_task
                src = screenshot_path
                if not src:
                    # Use atlas purpose for screenshots that will be used for learning
                    src = await asyncio.to_thread(
                        adb_driver.screenshot,
                        device_id=device_id,
                        purpose="atlas",
                        bundle_id=bundle_id
                    )

                # Fire background task with bundle_id for proper organization
                map_observed_ui_task.delay(
                    image_source=src,
                    device_id=device_id,
                    platform="android",
                    bundle_id=bundle_id
                )
                logger.info(f"[Harvest] Background mapping triggered for {device_id}")
            except Exception as e:
                logger.warning(f"[Harvest] Failed to trigger: {e}")

        async def check_risk_confirmation(name: str | None = None, input_val: str | None = None):
            """Phase 6: Interactive Safety Guard - Intercept high-risk keywords."""
            targets = [t for t in [name, input_val] if t]
            for t in targets:
                t_low = t.lower()
                if any(kw.lower() in t_low for kw in RISK_KEYWORDS):
                    logger.warning(f"[Safety] High-risk action detected for '{t}'. Intercepting...")
                    return f"ERR_CONFIRMATION_REQUIRED: The action involves sensitive operations ('{t}'). Please ask the user to confirm before proceeding with this specific step."
            return None

        async def validate_outcome(before_pkg: str, expected_pkg: str | None = None):
            """Phase 4: Post-Action Validation - Detect unexpected transitions."""
            await asyncio.sleep(0.8)  # Wait for UI to settle
            curr = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            curr_pkg = curr.get("package")
            if curr_pkg != before_pkg and expected_pkg and curr_pkg != expected_pkg:
                logger.warning(f"[Validation] Drift suspected: {before_pkg} -> {curr_pkg}")
                return False
            return True

        async def finish_action(msg: str) -> str:
            """Phase 4/6: Restore wait_after_ms logic."""
            if wait_after_ms > 0:
                await asyncio.sleep(wait_after_ms / 1000.0)
                return f"{msg} (waited {wait_after_ms}ms)"
            return msg

        async def resolve_element(name: str, role: str | None = None, timeout: float = 8.0, expected_pkg: str | None = None) -> dict | str:
            """Reactor: High-frequency poll for element with fallback.

            Optimizations:
            1. Exponential backoff: Initial 200ms, gradually increasing to 1s
            2. Sentinel interval check: Every 1s instead of every loop
            3. OCR limit: Max 2 attempts to reduce resource usage
            """
            start_time = time.time()
            target_norm = normalize_text(name)

            # Phase 4: Initial intercept
            await flash_intercept()

            is_h5 = await probe_hybrid()

            # Optimization 1: Exponential backoff (start at 200ms, max 1s)
            retry_delay = 0.2

            # Optimization 3: Limit OCR attempts
            ocr_attempts = 0
            max_ocr_attempts = 2

            last_sentinel_check = start_time

            while time.time() - start_time < timeout:
                loop_start = time.time()

                # Optimization 2: Sentinel interval check (every 1s)
                if expected_pkg and (loop_start - last_sentinel_check >= 1.0):
                    await check_sentinel(expected_pkg)
                    last_sentinel_check = loop_start

                # 1. Try A11y (Native)
                a11y_result = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=device_id)
                if a11y_result.success and a11y_result.elements:
                    candidates = []
                    for el in a11y_result.elements:
                        el_text = normalize_text(el.text)
                        el_res_id = normalize_text(el.metadata.get("resource_id", ""))
                        el_class = str(el.metadata.get("class", "")).lower()

                        score = 0
                        if target_norm == el_text: score = 100
                        elif target_norm in el_text: score = 50
                        elif target_norm in el_res_id: score = 30

                        if score > 0:
                            if role and role.lower() in el_class:
                                score += 20
                            candidates.append((score, el))

                    if candidates:
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        best_el = candidates[0][1]
                        logger.info(f"[Mobile] Resolved '{name}' via A11y (Score: {candidates[0][0]}) in {time.time()-start_time:.1f}s")
                        return {"x": best_el.x, "y": best_el.y}

                # 2. Try Atlas Fallback (Historical) - after 1.5s
                elapsed = time.time() - start_time
                if elapsed > 1.5:
                    try:
                        curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                        bundle_id = curr_app.get("package")
                        if bundle_id:
                            summary = await atlas_engine.store.get_app_summary(bundle_id)
                            stored_hash = summary.get("version_hash", "")

                            # Phase 6: Version Drift Fallback
                            is_stale = False
                            if stored_hash:
                                try:
                                    pkg_meta = await asyncio.to_thread(adb_driver.get_package_info, bundle_id, device_id=device_id)
                                    dummy = AtlasApp(app_name=bundle_id, bundle_id=bundle_id, platform="android")
                                    live_hash = dummy.compute_version_hash(
                                        str(pkg_meta.get("version_name", "0")),
                                        str(pkg_meta.get("last_update_time", "0"))
                                    )
                                    if live_hash != stored_hash:
                                        is_stale = True
                                        logger.warning(f"[Mobile] Bypassing stale Atlas data (v:{stored_hash} vs live:{live_hash})")
                                except:
                                    pass

                            if not is_stale and summary and "states" in summary:
                                for state in summary["states"][:3]:
                                    detail = await atlas_engine.store.get_state_detail(bundle_id, state["id"])
                                    for el in detail.get("elements", []):
                                        if name.lower() in str(el.get("label", "")).lower():
                                            logger.info(f"[Mobile] Resolved '{name}' via Atlas Prior")
                                            return {"x": el["x"], "y": el["y"]}
                    except:
                        pass

                # 3. Try Vision OCR (Hybrid/H5 Fallback) - with attempt limit
                # Optimization 3: Only attempt OCR max 2 times
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
                                    logger.info(f"[Mobile] Resolved '{name}' via OCR (Hybrid Mode, attempt {ocr_attempts}/{max_ocr_attempts})")
                                    return {"x": el.x, "y": el.y}
                    except Exception as e:
                        logger.debug(f"[Mobile] OCR attempt {ocr_attempts} failed: {e}")

                # Optimization 1: Exponential backoff with 1s cap
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 1.0)

            return f"ERR_ELEMENT_NOT_FOUND: Could not find element '{name}' on device."

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
            msg = f"Screenshot: {filepath}"
            if ocr:
                ocr_res = await vision_engine.process(VisionTask.OCR, filepath, on_android=True, device_id=device_id)
                if ocr_res.success and ocr_res.elements:
                    msg += "\n\n### OCR Results (Detected Text & Coordinates):\n"
                    msg += "\n".join([el.to_prompt_line() for el in ocr_res.elements])
                else:
                    msg += "\n\n(OCR requested but no text detected)"

            return await finish_action(msg)

        elif action in ["tap", "click"]:
            # Phase 6: Safety Guard
            risk_error = await check_risk_confirmation(name=element_name)
            if risk_error:
                return risk_error

            tx, ty = x, y
            curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            base_pkg = curr_app.get("package")

            if element_name:
                resolved = await resolve_element(element_name, element_role, expected_pkg=base_pkg, timeout=timeout)
                if isinstance(resolved, str):
                    return resolved
                tx, ty = resolved["x"], resolved["y"]
            else:
                # Handle relative coordinates
                if any(isinstance(v, float) for v in [tx, ty]):
                    sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                    tx = int(tx * sw) if isinstance(tx, float) else tx
                    ty = int(ty * sh) if isinstance(ty, float) else ty

            if tx is None or ty is None:
                return "Error: Coordinates or element_name required."

            await asyncio.to_thread(adb_driver.tap, tx, ty, device_id=device_id)

            # Phase 5: Automated Harvesting
            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(f"Tapped at ({tx}, {ty})" + (f" (resolved from '{element_name}')" if element_name else ""))

        elif action == "long_press":
            # Phase 6: Safety Guard
            risk_error = await check_risk_confirmation(name=element_name)
            if risk_error:
                return risk_error

            tx, ty = x, y
            curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            base_pkg = curr_app.get("package")

            if element_name:
                resolved = await resolve_element(element_name, element_role, expected_pkg=base_pkg, timeout=timeout)
                if isinstance(resolved, str):
                    return resolved
                tx, ty = resolved["x"], resolved["y"]
            else:
                # Handle relative coordinates
                if any(isinstance(v, float) for v in [tx, ty]):
                    sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                    tx = int(tx * sw) if isinstance(tx, float) else tx
                    ty = int(ty * sh) if isinstance(ty, float) else ty

            if tx is None or ty is None:
                return "Error: Coordinates or element_name required."

            # Long press = swipe to same position with longer duration
            press_duration = duration_ms if duration_ms > 300 else 800
            await asyncio.to_thread(adb_driver.long_press, tx, ty, duration_ms=press_duration, device_id=device_id)
            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(f"Long-pressed at ({tx}, {ty}) for {press_duration}ms" + (f" (resolved from '{element_name}')" if element_name else ""))

        elif action == "swipe":
            # Phase 6: Safety Guard
            risk_error = await check_risk_confirmation(name=element_name)
            if risk_error:
                return risk_error

            if any(v is None for v in [x, y, x2, y2]):
                return "Error: Need x, y, x2, y2."

            sw, sh = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
            # Handle float relative coordinates
            rx, ry = (int(x * sw) if isinstance(x, float) else x), (int(y * sh) if isinstance(y, float) else y)
            rx2, ry2 = (int(x2 * sw) if isinstance(x2, float) else x2), (int(y2 * sh) if isinstance(y2, float) else y2)

            await asyncio.to_thread(adb_driver.swipe, rx, ry, rx2, ry2, duration_ms=duration_ms, device_id=device_id)

            # Phase 5: Automated Harvesting
            curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            base_pkg = curr_app.get("package")
            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(f"Swiped from ({rx}, {ry}) to ({rx2}, {ry2})")

        elif action == "input_text":
            if not text:
                return "Error: 'text' required."

            # Phase 6: Safety Guard
            risk_error = await check_risk_confirmation(name=element_name, input_val=text)
            if risk_error:
                return risk_error

            curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            base_pkg = curr_app.get("package")

            if element_name:
                # Tap first to focus
                resolved = await resolve_element(element_name, element_role, expected_pkg=base_pkg, timeout=timeout)
                if isinstance(resolved, str):
                    return resolved
                await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                await asyncio.sleep(0.5)  # Wait for keyboard/focus

            await asyncio.to_thread(adb_driver.input_text, text, device_id=device_id)

            # Phase 5: Automated Harvesting
            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(f"Input text: {text[:50]}..." + (f" (focused on '{element_name}')" if element_name else ""))

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

            # Use 'text' argument as package name
            await asyncio.to_thread(adb_driver.launch_app, text, device_id=device_id)
            return await finish_action(f"Opened: {text}")

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

            # Truncate if extreme (200k chars is usually enough for complex apps)
            if len(xml) > 200000:
                xml = xml[:200000] + "\n...(truncated)"

            return await finish_action(f"UI Hierarchy:\n{xml}")

        elif action == "intent_flow":
            if not intents:
                return "Error: 'intents' list is required for intent_flow."

            steps_done = 0
            # Phase 4: Track package for sentinel
            curr = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
            base_pkg = curr.get("package")
            if base_pkg == "com.android.launcher3":
                base_pkg = None  # Start fresh

            for it in intents:
                act = it.get("action")
                target = it.get("target") or it.get("element_name")

                # Phase 6: Safety Guard
                risk_error = await check_risk_confirmation(name=target, input_val=it.get("text"))
                if risk_error:
                    return risk_error

                if act == "click" and target:
                    resolved = await resolve_element(target, expected_pkg=base_pkg, timeout=timeout)
                    if isinstance(resolved, str):
                        return resolved

                    await asyncio.to_thread(adb_driver.tap, resolved["x"], resolved["y"], device_id=device_id)
                    # Phase 4: Validate outcome
                    if not await validate_outcome(base_pkg):
                        await check_sentinel(base_pkg)  # Force recovery if drifted
                elif act == "input" and it.get("text"):
                    await asyncio.to_thread(adb_driver.input_text, it["text"], device_id=device_id)

                steps_done += 1
                await asyncio.sleep(0.5)  # Minimum transition wait

            # Phase 5: Automated Harvesting - with proper organization
            asyncio.create_task(trigger_atlas_harvest(bundle_id=base_pkg))
            return await finish_action(f"Successfully executed intent flow with {steps_done} steps.")

        elif action == "read_sms":
            # 'text' parameter is used as the regex_pattern, 'timeout' as polling max wait
            pattern = text if text else r'\d{4,6}'
            wait_time = int(timeout) if timeout else 30

            logger.info(f"Polling SMS inbox for pattern '{pattern}' up to {wait_time}s...")
            messages = await asyncio.to_thread(
                adb_driver.read_sms,
                regex_pattern=pattern,
                timeout=wait_time,
                device_id=device_id
            )

            if not messages:
                return await finish_action(f"No SMS matching pattern '{pattern}' received within {wait_time} seconds.")

            latest = messages[0]
            if latest.get("extract"):
                return await finish_action(
                    f"SMS Received! Extracted Match: {latest['extract']}\nFull Body: {latest['body']}")
            else:
                return await finish_action(f"SMS Received: {latest['body']}")

        return f"Error: Unknown action '{action}'."

    except ADBError as e:
        return f"⚠️ ADB ERROR: {e}"

    except Exception as e:
        logger.error(f"Mobile control error: {e}")
        return f"Error: {str(e)}"
