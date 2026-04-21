import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.core.environment.capabilities.registry import ActionRegistry
from app.core.execution.macro.schema import MacroSource, MacroStep, MacroStepType
from app.core.monitoring.activity import activity_monitor
from app.utils.geometry import parse_bounds
from app.utils.xml import clean_xml_content

logger = logging.getLogger(__name__)


class MacroEngine:
    """
    Standardized Macro Executer for Learned Skills.
    Interprets MacroScript models and executes them against domain tools.
    """

    @classmethod
    async def execute(
        cls,
        thread_id: str,
        script: Any, # MacroScript
        params: dict[str, Any] | None = None,
        extracted_data: dict[str, Any] | None = None,
        disable_ocr: bool = True
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Public entry point for MacroScript execution.

        Args:
            disable_ocr: If True, disables OCR fallback in element resolution for faster execution.
                        Default is True for deterministic macro execution.
        """
        return await cls.execute_steps(
            thread_id=thread_id,
            steps=script.steps,
            params=params,
            extracted_data=extracted_data,
            disable_ocr=disable_ocr,
            active_bundle_id=params.get("package_name") or params.get("bundle_id") if params else None
        )

    @classmethod
    async def execute_steps(
        cls,
        thread_id: str,
        steps: list[MacroStep],
        params: dict[str, Any] | None = None,
        extracted_data: dict[str, Any] | None = None,
        disable_ocr: bool = True,
        active_bundle_id: str | None = None
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Internal recursive execution of macro steps.
        Returns (success, message, fallback_context).

        Args:
            disable_ocr: If True, disables OCR fallback in element resolution for faster execution.
                        Default is True for deterministic macro execution.
        """
        if extracted_data is None:
            extracted_data = {}
        if params is None:
            params = {}

        for step in steps:
            step_num = step.step_number

            # 1. Parameter Injection (Handled at step level)
            target_selector = cls._inject_params(step.target_selector, params)
            payload = cls._inject_payload_params(step.payload, params)

            # Fallback for selector buried in payload
            target_selector = target_selector or payload.get("selector")

            # --- Observability: Log BEFORE processing ---
            desc = f"Execute Macro Step {step_num}: {step.type} "
            if step.type == MacroStepType.ACTION:
                desc = f"Execute Macro Step {step_num}: {step.event_type} "
                if target_selector:
                    desc += f"on {target_selector}"
                elif "url" in payload:
                    desc += f"to {payload['url']}"
            elif step.type == MacroStepType.LOOP:
                if payload.get("items_key"):
                    desc += f"(items_key='{payload.get('items_key')}')"
                else:
                    max_iters = payload.get("max_iterations", step.max_iterations)
                    desc += f"(max_iterations={max_iters})"
            elif step.type == MacroStepType.EXTRACT:
                desc += f"(key='{step.key}')"

            await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
            logger.info(f"[{thread_id}] {desc}")

            # 2. Handle Control Flow
            if step.type in (MacroStepType.CONTROL, MacroStepType.IF, MacroStepType.LOOP):
                success, msg, fallback = await cls._handle_control_flow(
                    thread_id, step, payload, params, extracted_data, disable_ocr, active_bundle_id
                )
                if not success:
                    return False, msg, fallback
                continue

            # 3. Handle Extraction
            if step.type == MacroStepType.EXTRACT:
                await cls._handle_extraction(thread_id, step, target_selector, payload, params, extracted_data)
                continue

            # 4. Handle Data Sink (Dump)
            if step.type == MacroStepType.DUMP:
                await cls._handle_dump(thread_id, payload, extracted_data)
                continue

            # 5. Handle Native Script (Bridge)
            if step.type == MacroStepType.NATIVE:
                await cls._handle_native(thread_id, payload, extracted_data)
                continue

            # 5. Handle UI Action
            if step.type == MacroStepType.ACTION:
                event_type = step.event_type
                source = step.source

                # Update active_bundle_id if this is an open_app step
                if event_type == "open_app": # Assuming MacroActionType.OPEN_APP is "open_app"
                    new_pkg = payload.get("package_name") or payload.get("package") or payload.get("text") or payload.get("app_name")
                    if new_pkg:
                        active_bundle_id = new_pkg
                        logger.info(f"[{thread_id}] Active package updated to: {active_bundle_id}")

                try:
                    if source == MacroSource.DOM:
                        await cls._execute_browser_step(event_type, target_selector, payload)
                    elif source == MacroSource.MOBILE:
                        await cls._execute_mobile_step(event_type, target_selector, payload, disable_ocr, expected_pkg=active_bundle_id)
                    elif source == MacroSource.DESKTOP:
                        await cls._execute_desktop_step(event_type, target_selector, payload)
                    else:
                        logger.warning(f"Unknown macro source: {source}")
                except Exception as e:
                    error_msg = str(e)

                    # --- Observability: Capture screenshot on failure ---
                    screenshot_path = None
                    try:
                        if source == MacroSource.DOM:
                            from app.core.environment.controllers.browser_controller import (
                                BrowserController,
                            )

                            # Use 'debug' purpose which exists in ScreenshotPurpose enum
                            res = await BrowserController.execute(action="screenshot", purpose="debug")
                            match = re.search(r"(/.*\.png)", str(res))
                            screenshot_path = match.group(1) if match else None
                    except Exception as se:
                        logger.error(f"Failed to capture failure screenshot: {se}")

                    fallback_context = {
                        "failed_step": step.model_copy().model_dump(),
                        "error_message": error_msg,
                        "source": source,
                        "screenshot": screenshot_path
                    }

                    if screenshot_path:
                        await activity_monitor.log_event("macro_thought", {
                            "text": f"[FAILED] Step {step_num} failed. Failure captured: {screenshot_path}"
                        }, thread_id)
                        logger.error(f"[{thread_id}] [FAILED] Macro Step {step_num} failed. Screenshot: {screenshot_path}")

                    return False, f"Step {step_num} failed: {error_msg}", fallback_context

                await activity_monitor.check_cancellation(thread_id)
                # Configurable delay between steps for better stability (default to 100ms instead of 1000ms)
                delay_ms = payload.get("delay_after_ms", 100)
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)

        return True, "", None

    @classmethod
    async def _handle_control_flow(cls, thread_id: str, step: MacroStep, payload: dict, params: dict, extracted_data: dict, disable_ocr: bool = True, active_bundle_id: str | None = None):
        if params is None:
            params = {}
        # Implementation of If/While/Loop logic
        condition = step.condition
        cond_type = condition.type if condition else None
        selector = cls._inject_params(condition.target_selector, params) if condition else None

        if step.type in (MacroStepType.CONTROL, MacroStepType.IF):
            if not condition:
                logger.warning(f"[{thread_id}] IF/CONTROL step {step.step_number} missing condition. Skipping.")
                return True, "", None
            is_true = await cls._evaluate_condition(cond_type, selector, step.source)
            branch = step.then_steps if is_true else step.else_steps
            if branch:
                return await cls.execute_steps(thread_id, branch, params, extracted_data, disable_ocr, active_bundle_id)

        elif step.type == MacroStepType.LOOP:
            # Check for collect_mode (two-phase batch collection)
            collect_mode = step.collect_mode
            if collect_mode in ("list", "detail", "auto"):
                return await cls._handle_collect_loop(
                    thread_id, step, payload, params, extracted_data, disable_ocr, collect_mode, active_bundle_id
                )

            # 1. Batch Loop Mode (if payload contains items_key)
            if payload.get("items_key"):
                return await cls._handle_loop(thread_id, step, payload, params, extracted_data, disable_ocr, active_bundle_id)

            # 2. Conditional Loop Mode (Standard While)
            iterations = 0
            if not step.steps:
                return True, "", None

            # Extract max_iterations from payload if present (allowing for parameter injection)
            max_iters = payload.get("max_iterations", step.max_iterations)
            if isinstance(max_iters, str):
                try:
                    max_iters = int(max_iters)
                except ValueError:
                    # If it's an unresolved template like {{max_scrolls}}, use a safe default
                    max_iters = 5

            while iterations < max_iters:
                is_true = await cls._evaluate_condition(cond_type, selector, step.source)
                if not is_true:
                    break

                loop_params = dict(params) if params else {}
                loop_params["loop_index"] = iterations

                # Execute nested steps
                success, msg, fallback = await cls.execute_steps(thread_id, step.steps, loop_params, extracted_data, disable_ocr, active_bundle_id)

                if not success:
                    # Enrich fallback with loop progress
                    if not fallback:
                        fallback = {"failed_step": step.model_copy().model_dump()}

                    fallback["loop_progress"] = {
                        "loop_step_number": step.step_number,
                        "current_iteration": iterations,
                        "max_iterations": max_iters,
                        "condition": cond_type
                    }
                    return False, msg, fallback

                iterations += 1

            if iterations >= max_iters:
                logger.warning(f"[{thread_id}] While loop reached max iterations ({max_iters})")

        return True, "", None

    @classmethod
    async def _handle_loop(cls, thread_id: str, step: MacroStep, payload: dict, params: dict, extracted_data: dict, disable_ocr: bool = True, active_bundle_id: str | None = None):
        """
        Handle a batch loop by iterating over a list of items and executing nested steps.
        Includes exponential backoff for network errors and DLQ support.
        Phase 3: Integrates DynamicAppTriage for autonomous scrolling.
        """
        items_key = payload.get("items_key", "items")
        items = extracted_data.get(items_key) or params.get(items_key)

        if not items or not isinstance(items, list):
            # Fuzzy matching: if there's only one list in extracted_data, use it
            lists = {k: v for k, v in extracted_data.items() if isinstance(v, list)}
            if len(lists) == 1:
                items_key = list(lists.keys())[0]
                items = lists[items_key]
                logger.info(f"[{thread_id}] Using fuzzy match for loop: key '{items_key}' found instead of '{payload.get('items_key')}'")
                await activity_monitor.log_event("macro_thought", {"text": f"Using fuzzy match: '{items_key}'"}, thread_id)
            else:
                warn_msg = f"[WARNING] Batch loop skipped: No items found for key '{items_key}'"
                logger.warning(f"[{thread_id}] {warn_msg}")
                await activity_monitor.log_event("macro_thought", {"text": warn_msg}, thread_id)
                return True, "", None

        logger.info(f"[{thread_id}] Starting Batch Loop: {len(items)} items for key '{items_key}'")
        await activity_monitor.log_event("macro_thought", {"text": f"Starting loop ({len(items)} items)"}, thread_id)

        # Phase 3: Dynamic App Awareness
        is_dynamic = False
        bundle_id = None
        if step.source == MacroSource.MOBILE:
            try:
                from app.core.environment.controllers.mobile_controller import (
                    MobileController,
                )
                from app.core.context.manager import ContextManager
                from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
                from app.infrastructure.drivers.adb import adb_driver

                device_id = ContextManager.get_var("device_id")
                curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                bundle_id = curr_app.get("package")
                if bundle_id:
                    dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform="android")
                    is_dynamic = bundle_id in dynamic_apps
            except Exception as e:
                logger.warning(f"Failed to detect dynamic status: {e}")

        max_retries = payload.get("max_retries", 3)
        backoff_base = payload.get("backoff_base", 2)

        dlq = []

        for index, item in enumerate(items):
            retry_count = 0
            success = False
            last_error = ""

            # For dynamic apps, we allow one 'scroll and retry' if the first attempt fails
            scroll_attempts = 1 if is_dynamic else 0
            current_scroll_attempt = 0

            while retry_count <= max_retries:
                try:
                    # 1. Prepare iteration context
                    iter_params = dict(params or {})
                    iter_params["item"] = item
                    iter_params["batch_index"] = index

                    # 2. Execute nested steps (unified)
                    success, msg, fallback = await cls.execute_steps(thread_id, step.steps, iter_params, extracted_data, disable_ocr, active_bundle_id)

                    if success:
                        break

                    last_error = msg
                    # Determine if it's a network error
                    is_network_error = any(kw in msg.lower() for kw in ["network", "timeout", "connection", "http", "status 50", "429"])

                    if is_network_error:
                        sleep_time = backoff_base ** retry_count
                        logger.warning(f"[{thread_id}] Network error in batch iteration {index}. Retrying in {sleep_time}s... Error: {msg}")
                        await asyncio.sleep(sleep_time)
                        retry_count += 1
                    elif "ERR_ELEMENT_NOT_FOUND" in msg and current_scroll_attempt < scroll_attempts:
                        from app.core.environment.controllers.mobile_controller import MobileController

                        # Phase 3: Autonomous Scrolling for Dynamic Apps
                        logger.info(f"[{thread_id}] Element not found in dynamic app. Attempting autonomous scroll...")
                        await MobileController.execute(action="swipe", direction="up", duration_ms=800)
                        await asyncio.sleep(1) # Wait for UI to settle
                        current_scroll_attempt += 1
                        # We don't increment retry_count here, just retry the same iteration after scroll
                        continue
                    else:
                        # Non-network and non-scrollable error (e.g. fatal UI change)
                        logger.error(f"[{thread_id}] Functional error in batch iteration {index}: {msg}")
                        return False, msg, fallback

                except Exception as e:
                    last_error = str(e)
                    logger.error(f"[{thread_id}] Unexpected error in batch iteration {index}: {e}")
                    retry_count += 1
                    await asyncio.sleep(backoff_base ** retry_count)

            if not success:
                logger.error(f"[{thread_id}] Batch item {index} failed after {max_retries} retries. Moving to DLQ.")
                dlq.append({"item": item, "error": last_error, "index": index})

        if dlq:
            # Persistent DLQ logging (to be expanded to a DB table if needed)
            logger.error(f"[{thread_id}] Batch completed with {len(dlq)} errors in DLQ: {dlq}")
            # For now, we return success so the whole batch isn't considered a fatal failure,
            # but we could also return partial success status.
            return True, f"Completed with {len(dlq)} items in DLQ", {"dlq": dlq}

        return True, "", None

    @classmethod
    async def _handle_collect_loop(
        cls,
        thread_id: str,
        step: MacroStep,
        payload: dict,
        params: dict,
        extracted_data: dict,
        disable_ocr: bool,
        collect_mode: str,
        active_bundle_id: str | None = None
    ) -> tuple[bool, str, dict | None]:
        """
        Handle two-phase batch collection loop.

        Phases:
        - LIST: Collect items from multiple screens without executing nested steps
        - DETAIL: Execute nested steps for each collected item
        - AUTO: Run LIST then DETAIL automatically

        State is persisted to a JSON file for resumability.
        """
        # Configuration
        state_file = payload.get("state_file", f"/tmp/macro_collect_{thread_id}.json")
        list_config = payload.get("list_config", {})
        detail_config = payload.get("detail_config", {})

        # Load or initialize state
        state = {"items": [], "phase": "list", "created_at": datetime.now().isoformat()}
        if os.path.exists(state_file):
            try:
                with open(state_file, encoding='utf-8') as f:
                    state = json.load(f)
            except Exception as e:
                logger.warning(f"[{thread_id}] Failed to load state file, starting fresh: {e}")

        # Phase 1: LIST - Collect items from screens
        if (collect_mode in ("list", "auto")) and (state["phase"] == "list" or collect_mode == "list"):
            logger.info(f"[{thread_id}] Starting LIST phase for batch collection")
            await activity_monitor.log_event("macro_thought", {"text": "Starting list collection phase"}, thread_id)

            max_screens = int(list_config.get("max_screens", 10))
            swipe_distance = int(list_config.get("swipe_distance", 1200))
            wait_ms = int(list_config.get("wait_after_swipe_ms", 1500))

            # Extract rules
            anchor_rule = list_config.get("anchor_element", {"type": "price", "pattern": "￥[0-9,.]+"})
            feature_config = list_config.get("feature_region", {"offset_y": -200, "height": 200, "max_features": 4})

            seen_signatures = {item["signature"] for item in state["items"]}
            new_items_count = 0

            for screen_num in range(max_screens):
                logger.info(f"[{thread_id}] Collecting screen {screen_num + 1}/{max_screens}")

                # Get UI dump
                try:
                    if step.source == MacroSource.MOBILE:
                        from app.infrastructure.drivers.adb import adb_driver
                        device_id = params.get("device_id")
                        xml = await asyncio.to_thread(adb_driver.dump_ui, device_id, compressed=False)
                    else:
                        raise NotImplementedError(f"Collect mode not implemented for source: {step.source}")
                except Exception as e:
                    logger.error(f"[{thread_id}] Failed to get UI dump: {e}")
                    break

                # Parse and extract items
                items = cls._extract_collect_items_from_xml(xml, anchor_rule, feature_config)

                # Deduplicate and add to state
                for item in items:
                    if item["signature"] not in seen_signatures:
                        seen_signatures.add(item["signature"])
                        item["status"] = "pending"
                        item["collected_at"] = datetime.now().isoformat()
                        item["screen_num"] = screen_num + 1
                        state["items"].append(item)
                        new_items_count += 1

                logger.info(f"[{thread_id}] Screen {screen_num + 1}: found {len(items)}, new {new_items_count}")

                # Check if we should continue
                if screen_num >= max_screens - 1:
                    break

                # Scroll to next screen
                try:
                    from app.core.environment.controllers.mobile_controller import MobileController

                    # Map swipe_distance to a ratio for the 'scroll' action
                    # Standard height is ~2400. 1200 is 0.5
                    scroll_ratio = min(0.9, max(0.1, swipe_distance / 2400.0 if swipe_distance > 1 else 0.5))

                    res = await MobileController.execute(
                        action="scroll",
                        direction="down",  # 'swipe up' is 'scroll down'
                        scroll_amount=scroll_ratio,
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )

                    if isinstance(res, str) and (res.startswith("Error") or res.startswith("ERR_")):
                        logger.error(f"[{thread_id}] Scroll failed: {res}")
                        break

                    await asyncio.sleep(wait_ms / 1000)
                except Exception as e:
                    logger.error(f"[{thread_id}] Scroll action exception: {e}")
                    break

            state["phase"] = "detail"
            state["updated_at"] = datetime.now().isoformat()
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            logger.info(f"[{thread_id}] LIST phase complete: {len(state['items'])} items collected")
            await activity_monitor.log_event("macro_thought", {"text": f"List collection complete: {len(state['items'])} items"}, thread_id)

            if collect_mode == "list":
                # Only list mode, return success
                extracted_data["collected_items"] = state["items"]
                extracted_data["collect_state_file"] = state_file
                return True, f"List collection complete: {len(state['items'])} items", {"state_file": state_file}

        # Phase 2: DETAIL - Execute steps for each collected item
        if collect_mode in ("detail", "auto") and state["phase"] in ("detail", "completed"):
            logger.info(f"[{thread_id}] Starting DETAIL phase for batch collection")
            await activity_monitor.log_event("macro_thought", {"text": "Starting detail execution phase"}, thread_id)

            pending_items = [item for item in state["items"] if item.get("status") == "pending"]
            if not pending_items:
                logger.info(f"[{thread_id}] No pending items to process")
                return True, "No pending items", None

            limit = int(detail_config.get("limit"))
            if limit:
                pending_items = pending_items[:limit]

            success_count = 0
            fail_count = 0

            for i, item in enumerate(pending_items):
                logger.info(f"[{thread_id}] Processing item {i+1}/{len(pending_items)}: {item['signature'][:50]}")

                try:
                    from app.core.environment.controllers.mobile_controller import MobileController

                    # Tap to open detail
                    tap_x = item.get("tap_x", 540)
                    tap_y = item.get("tap_y", item.get("anchor_y", 500))

                    await MobileController.execute(
                        action="click",
                        x=tap_x,
                        y=tap_y,
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )
                    await asyncio.sleep(detail_config.get("wait_after_tap_ms", 2000) / 1000)

                    # Execute nested steps for detail collection
                    if step.steps:
                        iter_params = dict(params)
                        iter_params["item"] = item
                        iter_params["item_index"] = i
                        iter_params["collected_signature"] = item["signature"]

                        success, msg, fallback = await cls.execute_steps(
                            thread_id, step.steps, iter_params, extracted_data, disable_ocr, active_bundle_id
                        )

                        if not success:
                            logger.warning(f"[{thread_id}] Detail steps failed for item {i}: {msg}")
                            item["status"] = "failed"
                            item["error"] = msg
                            fail_count += 1
                        else:
                            item["status"] = "done"
                            item["completed_at"] = datetime.now().isoformat()

                            # NEW: Capture extraction results into the item for persistence/dumping
                            capture_config = detail_config.get("data_capture")
                            if capture_config:
                                for target_key, source_key in capture_config.items():
                                    val = extracted_data.get(source_key)
                                    if val is not None:
                                        item[target_key] = val
                                logger.info(f"[{thread_id}] Captured {len(capture_config)} fields into item {i}")

                            success_count += 1
                    else:
                        # No nested steps, just mark as done
                        item["status"] = "done"
                        item["completed_at"] = datetime.now().isoformat()
                        success_count += 1

                    # Go back to list
                    from app.core.environment.controllers.mobile_controller import MobileController

                    await MobileController.execute(
                        action="press_key",
                        keycode=4,  # BACK
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )
                    await asyncio.sleep(0.8)

                except Exception as e:
                    logger.error(f"[{thread_id}] Error processing item {i}: {e}")
                    item["status"] = "failed"
                    item["error"] = str(e)
                    fail_count += 1

                # Save progress every 5 items
                if i % 5 == 0:
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)

            # Final save
            state["phase"] = "completed"
            state["updated_at"] = datetime.now().isoformat()
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            result_msg = f"Detail phase complete: {success_count} succeeded, {fail_count} failed"
            logger.info(f"[{thread_id}] {result_msg}")
            await activity_monitor.log_event("macro_thought", {"text": f"{result_msg}"}, thread_id)

            extracted_data["collect_results"] = {
                "total": len(state["items"]),
                "success": success_count,
                "failed": fail_count,
                "state_file": state_file
            }
            return True, result_msg, {"state_file": state_file}

        return True, "Collect loop processed", None

    @staticmethod
    def _extract_collect_items_from_xml(xml_content: str, anchor_rule: dict, feature_config: dict) -> list[dict]:
        """Extract collectible items from UI dump XML."""
        import xml.etree.ElementTree as ET

        def _parse_bounds_local(bounds_str: str):
            """Local wrapper that returns default on failure."""
            bounds = parse_bounds(bounds_str)
            if bounds:
                return (bounds.x1, bounds.y1, bounds.x2, bounds.y2)
            return (0, 0, 0, 0)

        def is_anchor_match(text: str, rule: dict) -> bool:
            if not text:
                return False
            pattern = rule.get("pattern", "")
            if pattern and re.search(pattern, text):
                return True
            return False

        # Clean XML using utility function
        xml_content = clean_xml_content(xml_content)
        if not xml_content:
            return []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        items = []

        # Find all anchor elements
        for node in root.iter():
            text = node.get("text", "")
            if is_anchor_match(text, anchor_rule):
                bounds = _parse_bounds_local(node.get("bounds", ""))
                if bounds == (0, 0, 0, 0):
                    continue

                x1, y1, x2, y2 = bounds
                anchor_y = (y1 + y2) // 2
                anchor_x = (x1 + x2) // 2

                # Find feature elements near the anchor
                offset_y = feature_config.get("offset_y", -200)
                height = feature_config.get("height", 200)
                max_features = feature_config.get("max_features", 4)

                feature_y_min = anchor_y + offset_y
                feature_y_max = feature_y_min + height

                features = []
                for elem in root.iter():
                    elem_bounds = _parse_bounds_local(elem.get("bounds", ""))
                    if elem_bounds == (0, 0, 0, 0):
                        continue

                    ex1, ey1, ex2, ey2 = elem_bounds
                    elem_center_y = (ey1 + ey2) // 2

                    if feature_y_min <= elem_center_y <= feature_y_max:
                        elem_text = elem.get("text", "")
                        if elem_text and not is_anchor_match(elem_text, anchor_rule):
                            features.append(elem_text[:30])  # Truncate long text
                            if len(features) >= max_features:
                                break

                # Generate signature
                sig_parts = [text] + features[:2]
                signature = "|".join(sig_parts)

                items.append({
                    "anchor_text": text,
                    "anchor_y": anchor_y,
                    "anchor_x": anchor_x,
                    "tap_x": 540,  # Center of screen
                    "tap_y": anchor_y - 80,  # Slightly above anchor
                    "features": features,
                    "signature": signature
                })

        # Sort by Y position
        items.sort(key=lambda x: x["anchor_y"])
        return items

    @classmethod
    async def _evaluate_condition(cls, cond_type: str, selector: str, source: str) -> bool:
        from app.core.environment.controllers.browser_controller import BrowserController
        from app.core.environment.controllers.desktop_controller import DesktopController
        from app.core.environment.controllers.mobile_controller import MobileController

        if cond_type == "element_exists":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="check_element", selector=selector)
                return "Found" in str(res)
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(action="applescript", script=f'tell application "System Events" to exists (first UI element whose name contains "{selector}")')
                return "true" in str(res).lower()

        elif cond_type == "element_visible":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="check_element", selector=selector)
                return "visible=True" in str(res)
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(action="applescript", script=f'tell application "System Events" to get visible of (first UI element whose name contains "{selector}")')
                return "true" in str(res).lower()

        elif cond_type == "text_contains":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="get_text")
                return selector in str(res) if res else False
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(action="applescript", script=f'tell application "System Events" to get name of every UI element whose name contains "{selector}"')
                return len(str(res)) > 5

        elif cond_type in ("has_more_items", "more_items", "pagination_exists"):
            # For synthesis dry-runs, we default to True to allow testing the loop body
            # Real implementation could check screen scrollability or presence of 'Next' buttons
            return True

        return False

    @classmethod
    async def _handle_extraction(cls, thread_id: str, step: MacroStep, selector: str, payload: dict, params: dict, extracted_data: dict):
        from app.core.environment.controllers.browser_controller import BrowserController
        from app.core.environment.controllers.desktop_controller import DesktopController
        from app.core.environment.controllers.mobile_controller import MobileController

        key = cls._inject_params(step.key, params) or "data"
        extract_type = step.extract_type or step.event_type

        desc = f"Extract '{key}' from {selector}"
        await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)

        if step.source == MacroSource.DOM:
            call_kwargs = {"action": extract_type, "selector": selector}
            if extract_type == "get_attribute" and "attribute" in payload:
                call_kwargs["attribute"] = payload["attribute"]
            elif extract_type in ("run_js", "evaluate") and ("script" in payload or "expression" in payload):
                call_kwargs["action"] = "run_js"
                call_kwargs["script"] = payload.get("script") or payload.get("expression")

            res = await BrowserController.execute(**call_kwargs)
            if extract_type == "screenshot":
                match = re.search(r"(/.*\.png)", str(res))
                extracted_data[key] = match.group(1) if match else res
            else:
                try:
                    # Attempt to parse as JSON if it looks like a list or object
                    if isinstance(res, str) and (res.startswith("[") or res.startswith("{")):
                        extracted_data[key] = json.loads(res)
                    else:
                        extracted_data[key] = res
                except Exception:
                    extracted_data[key] = res

        elif step.source in (MacroSource.MOBILE, MacroSource.GLOBAL, MacroSource.DESKTOP):
            if extract_type == "gui_extract":
                await cls._handle_gui_extract(thread_id, step, selector, payload, params, extracted_data)
                return

            if extract_type == "dump_ui":
                if step.source == MacroSource.DESKTOP:
                    res = await DesktopController.execute(action="dump_ui")
                else:
                    res = await MobileController.execute(action="dump_ui")
                extracted_data[key] = res
            elif extract_type == "screenshot":
                if step.source == MacroSource.DESKTOP:
                    res = await DesktopController.execute(action="screenshot", region=payload.get("region"))
                else:
                    res = await MobileController.execute(action="screenshot", region=payload.get("region"))

                match = re.search(r"(/.*\.png)", str(res))
                filepath = match.group(1) if match else str(res)
                if selector and filepath.endswith(".png"):
                    if step.source == MacroSource.MOBILE:
                        filepath = await cls._crop_mobile_screenshot(filepath, selector)
                    # For DESKTOP, we might not have a specific crop helper yet if selector is complex
                extracted_data[key] = filepath

    @classmethod
    async def _handle_gui_extract(cls, thread_id: str, step: MacroStep, selector: str, payload: dict, params: dict, extracted_data: dict):
        """Handle Coordinate-based GUI extraction (OCR)."""
        from app.core.environment.controllers.desktop_controller import DesktopController
        from app.core.environment.controllers.mobile_controller import MobileController

        key = cls._inject_params(step.key, params) or "extracted_text"
        pos = payload.get("relative_position") or {"x": payload.get("x", 0.5), "y": payload.get("y", 0.5)}
        region = payload.get("region")

        # [Refactor] Route through controllers for unified logic
        try:
            if step.source == MacroSource.DESKTOP:
                res = await DesktopController.execute(
                    action="gui_extract",
                    x=pos.get("x"),
                    y=pos.get("y"),
                    region=region
                )
                extracted_data[key] = res
            elif step.source == MacroSource.MOBILE:
                res = await MobileController.execute(
                    action="gui_extract",
                    x=pos.get("x"),
                    y=pos.get("y"),
                    region=region,
                    extraction_method=payload.get("extraction_method")
                )

                # Deserialization check for structural results (like lists)
                if isinstance(res, str) and (res.startswith("[") or res.startswith("{")):
                    try:
                        extracted_data[key] = json.loads(res)
                    except:
                        extracted_data[key] = res
                else:
                    extracted_data[key] = res
            else:
                extracted_data[key] = None
        except Exception as e:
            logger.error(f"GUI Extract OCR failed: {e}")
            extracted_data[key] = None
        finally:
            # Clean up if needed (though controllers handle this now)
            pass

    @classmethod
    async def _crop_mobile_screenshot(cls, filepath: str, selector: str) -> str:
        try:
            from PIL import Image

            from app.core.vision.providers.native.android_a11y import android_a11y_provider
            from app.core.vision.types import VisionTask

            def _norm(t): return re.sub(r'\s+', '', t).lower() if t else ""
            a11y_res = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=None)

            if a11y_res.success:
                target_norm = _norm(selector)
                for el in a11y_res.elements:
                    if _norm(el.text) == target_norm or target_norm in _norm(el.metadata.get("resource_id", "")):
                        bounds = (el.x - el.width//2, el.y - el.height//2, el.x + el.width//2, el.y + el.height//2)
                        with Image.open(filepath) as img:
                            cropped = img.crop(bounds)
                            new_path = filepath.replace(".png", f"_crop_{_norm(selector)[:15]}.png")
                            cropped.save(new_path)
                            os.remove(filepath)
                            return new_path
        except Exception as e:
            logger.warning(f"MacroEngine cropping failed: {e}")
        return filepath

    @classmethod
    async def _handle_dump(cls, thread_id: str, payload: dict, extracted_data: dict):
        """Handle data persistence - supports file, MCP, and webhook sinks."""
        sink_type = payload.get("sink_type", "file")

        # Enrich data if requested from state file (for two-phase batch collection)
        data_to_dump = dict(extracted_data)
        if payload.get("include_state_items"):
            state_file = extracted_data.get("collect_results", {}).get("state_file")
            if state_file and os.path.exists(state_file):
                try:
                    with open(state_file, encoding='utf-8') as f:
                        state_data = json.load(f)
                        # We use 'items' for MCP batch tools
                        data_to_dump["batch_items"] = state_data.get("items", [])
                        logger.info(f"[{thread_id}] Enriched dump with {len(data_to_dump['batch_items'])} items from state file")
                except Exception as e:
                    logger.warning(f"[{thread_id}] Failed to load state file for enriched dump: {e}")

        if sink_type == "file":
            await cls._dump_to_file(thread_id, payload, data_to_dump)
        elif sink_type == "mcp":
            await cls._dump_to_mcp(thread_id, payload, data_to_dump)
        elif sink_type == "webhook":
            await cls._dump_to_webhook(thread_id, payload, data_to_dump)
        else:
            logger.warning(f"Unknown sink_type: {sink_type}, falling back to file")
            await cls._dump_to_file(thread_id, payload, data_to_dump)

    @classmethod
    async def _dump_to_file(cls, thread_id: str, payload: dict, extracted_data: dict):
        """Dump extracted data to local file."""
        sink_path = payload.get("path", f"/tmp/macro_results_{thread_id}.json")
        await activity_monitor.log_event("macro_thought", {"text": f"Dump extracted data to {sink_path}"}, thread_id)
        try:
            with open(sink_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[MacroEngine] Data dumped to file: {sink_path}")
        except Exception as e:
            logger.warning(f"Failed to dump data to file: {e}")

    @classmethod
    async def _dump_to_mcp(cls, thread_id: str, payload: dict, extracted_data: dict):
        """Push extracted data to an MCP server."""
        from app.core.mcp import mcp_client_manager

        mcp_server = payload.get("mcp_server", "supabase")
        mcp_tool_name = payload.get("mcp_tool")
        table = payload.get("table", "extracted_data")
        operation = payload.get("operation", "insert")

        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Pushing data to MCP server '{mcp_server}' using {mcp_tool_name or operation}"},
            thread_id
        )

        try:
            # Get tools from MCP server
            tools = await mcp_client_manager.get_tools(mcp_server)
            if not tools:
                logger.error(f"[MacroEngine] MCP server '{mcp_server}' not available")
                return

            # Find appropriate tool
            target_tool = None
            for tool in tools:
                # 1. Exact match OR formatted match (mcp__server__tool)
                if mcp_tool_name:
                    formatted_name = f"mcp__{mcp_server.replace(' ', '_').replace('-', '_')}__{mcp_tool_name.replace(' ', '_').replace('-', '_')}"
                    if tool.name == mcp_tool_name or tool.name == formatted_name:
                        target_tool = tool
                        break

                # 2. Fuzzy match by operation (fallback)
                if not mcp_tool_name:
                    tool_name = tool.name.lower()
                    if operation in tool_name or "insert" in tool_name or "store" in tool_name:
                        target_tool = tool
                        break

            if not target_tool:
                if mcp_tool_name:
                    logger.error(f"[MacroEngine] MCP tool '{mcp_tool_name}' not found on server '{mcp_server}'")
                    return
                # Extreme fallback
                target_tool = tools[0]
                logger.warning(f"[MacroEngine] Using total fallback MCP tool: {target_tool.name}")

            # Prepare data payload
            # Support generic data mapping if provided in the step payload
            mapping = payload.get("data_mapping")
            if mapping:
                data_payload = {}
                for target_key, source_key in mapping.items():
                    if source_key == "$thread_id":
                        data_payload[target_key] = thread_id
                    elif source_key == "$timestamp":
                        data_payload[target_key] = datetime.now(timezone.utc).isoformat()
                    else:
                        # Get value from extracted_data (could be simple key or batch_items)
                        data_payload[target_key] = extracted_data.get(source_key)

                # Check for empty payload
                if not data_payload:
                    logger.warning(f"[{thread_id}] MCP data_mapping resulted in empty payload")
            else:
                # Default behavior (backward compatible)
                data_payload = {
                    "table": table,
                    "data": extracted_data,
                    "thread_id": thread_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Call MCP tool
            result = await target_tool.ainvoke(data_payload)
            logger.info(f"[MacroEngine] Data pushed to MCP '{mcp_server}': {result}")

        except Exception as e:
            logger.error(f"[MacroEngine] Failed to push data to MCP: {e}", exc_info=True)

    @classmethod
    async def _dump_to_webhook(cls, thread_id: str, payload: dict, extracted_data: dict):
        """Push extracted data to a webhook URL."""
        import httpx

        webhook_url = payload.get("webhook_url")
        if not webhook_url:
            logger.error("[MacroEngine] webhook_url required for webhook sink_type")
            return

        headers = payload.get("headers", {})
        method = payload.get("method", "POST").upper()

        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Pushing data to webhook: {webhook_url}"},
            thread_id
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                request_data = {
                    "thread_id": thread_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": extracted_data
                }

                if method == "POST":
                    response = await client.post(webhook_url, json=request_data, headers=headers)
                elif method == "PUT":
                    response = await client.put(webhook_url, json=request_data, headers=headers)
                else:
                    logger.error(f"[MacroEngine] Unsupported HTTP method: {method}")
                    return

                response.raise_for_status()
                logger.info(f"[MacroEngine] Data pushed to webhook: {response.status_code}")

        except Exception as e:
            logger.error(f"[MacroEngine] Failed to push data to webhook: {e}", exc_info=True)

    @classmethod
    async def _handle_native(cls, thread_id: str, payload: dict, extracted_data: dict):
        """Execute an external script as a native step."""
        script_path = payload.get("script_path")
        command = payload.get("command", "python3")
        args = payload.get("args", [])
        sync_state = payload.get("sync_state")

        if not script_path:
            logger.error(f"[{thread_id}] No script_path provided for native step")
            return

        # Build full command
        cmd_list = [command, script_path] + [str(a) for a in args]
        cmd_str = " ".join(cmd_list)

        logger.info(f"[{thread_id}] Executing native script: {cmd_str}")
        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Running native script: {cmd_str}"},
            thread_id
        )

        try:
            # Run subprocess
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                logger.error(f"[{thread_id}] Native script failed with code {process.returncode}: {err_msg}")
            else:
                logger.info(f"[{thread_id}] Native script completed successfully")

            # Handle sync_state if provided
            if sync_state and os.path.exists(sync_state):
                try:
                    with open(sync_state, encoding='utf-8') as f:
                        state_data = json.load(f)

                    # Merge items into batch_items for dumping
                    items = state_data.get('items', [])
                    if items:
                        extracted_data["batch_items"] = items
                        logger.info(f"[{thread_id}] Synced {len(items)} items from {sync_state} to extracted_data")
                except Exception as sync_err:
                    logger.error(f"[{thread_id}] Failed to sync state from {sync_state}: {sync_err}")

        except Exception as e:
            logger.error(f"[{thread_id}] Failed to execute native script: {e}", exc_info=True)

    # --- Tool Invocation Wrappers (Browser/Mobile/Desktop) ---

    @classmethod
    async def _execute_browser_step(cls, event_type: str, selector: str, payload: dict):
        """Execute a browser step directly via BrowserController (no @evoloop_tool overhead)."""

        from app.core.environment.controllers import BrowserController

        # Normalize event_type to lowercase for case-insensitive comparison
        event_type = event_type.lower() if event_type else event_type
        continue_on_error = payload.get("continue_on_error", False)
        timeout_ms = payload.get("timeout_ms", 15000)

        def handle_res(res):
            if res and isinstance(res, str):
                if res.startswith("Warning:"):
                    return
                if "Execution failed:" in res or "Error:" in res:
                    if not continue_on_error:
                        raise ValueError(res)

        tool_action = ActionRegistry.get_tool_action(event_type, "dom")

        if event_type in ("goto", "navigate"):
            res = await BrowserController.execute(action=tool_action, url=payload.get("url"), timeout_ms=timeout_ms, continue_on_error=continue_on_error)
            handle_res(res)
            # Wait for page to stabilize after navigation
            await BrowserController.execute(action="wait_for_stability", timeout_ms=5000)
        elif event_type == "back":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "forward":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "reload":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type in ("click", "tap", "double_click", "hover"):
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, x=payload.get("x"), y=payload.get("y"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type in ("input", "type_text"):
            handle_res(await BrowserController.execute(action="type_text", selector=selector, value=payload.get("text") or payload.get("value", ""), clear_first=payload.get("clear_first", True), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "select_option":
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, value=payload.get("value"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "key_press":
            handle_res(await BrowserController.execute(action=tool_action, key=payload.get("key"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "drag_drop":
            handle_res(await BrowserController.execute(action=tool_action, source_selector=payload.get("source_selector") or selector, target_selector=payload.get("target_selector"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "upload":
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, file_path=payload.get("file_path"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "detect_pagination":
            handle_res(await BrowserController.execute(action="detect_pagination", timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "scroll_to_bottom":
            handle_res(await BrowserController.execute(action="scroll_to_bottom", selector=selector, payload=payload, timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "wait":
            duration = payload.get("seconds") or (payload.get("duration_ms", 1000) / 1000.0)
            await asyncio.sleep(float(duration))
        elif event_type == "wait_for":
            handle_res(await BrowserController.execute(action=tool_action, selector=payload.get("selector") or selector, state=payload.get("state", "visible"), url_pattern=payload.get("url_pattern"), timeout_ms=timeout_ms, continue_on_error=continue_on_error))
        elif event_type == "scroll":
            await BrowserController.execute(action=tool_action, selector=selector, direction=payload.get("direction", "down"), amount=payload.get("amount", 300), continue_on_error=continue_on_error)
        elif event_type == "screenshot":
            await BrowserController.execute(action=tool_action, selector=selector, full_page=payload.get("full_page", False), continue_on_error=continue_on_error)
        elif event_type == "new_tab":
            await BrowserController.execute(action=tool_action, url=payload.get("url"), continue_on_error=continue_on_error)
        elif event_type == "switch_tab":
            await BrowserController.execute(action=tool_action, tab_index=payload.get("tab_index"), continue_on_error=continue_on_error)
        elif event_type == "dialog_handle":
            await BrowserController.execute(action=tool_action, dialog_action=payload.get("dialog_action"), dialog_text=payload.get("dialog_text"), continue_on_error=continue_on_error)
        elif event_type in ("run_js", "evaluate"):
            await BrowserController.execute(action="run_js", script=payload.get("script") or payload.get("expression"), continue_on_error=continue_on_error)

    @classmethod
    async def _execute_desktop_step(cls, event_type: str, selector: str, payload: dict):
        """Execute a desktop step directly via DesktopController (no @evoloop_tool overhead)."""

        from app.core.environment.controllers import DesktopController

        # Normalize event_type to lowercase for case-insensitive comparison
        event_type = event_type.lower() if event_type else event_type
        selector = selector or payload.get("element_name") or payload.get("target")
        tool_action = ActionRegistry.get_tool_action(event_type, "desktop")

        def handle_res(res):
            if res and "Error:" in str(res):
                raise ValueError(res)

        if event_type in ("click", "tap", "double_click"):
            handle_res(await DesktopController.execute(action=tool_action, element_name=selector, x=payload.get("x"), y=payload.get("y")))
        elif event_type in ("input", "type_text"):
            handle_res(await DesktopController.execute(action="type_text", text=payload.get("text") or payload.get("value", ""), force_keystroke=payload.get("force_keystroke", False)))
        elif event_type == "key_press":
            handle_res(await DesktopController.execute(action=tool_action, key=payload.get("key")))
        elif event_type == "scroll":
            handle_res(await DesktopController.execute(action=tool_action, direction=payload.get("direction", "down"), amount=payload.get("amount", 300)))
        elif event_type == "drag_drop":
            handle_res(await DesktopController.execute(action=tool_action, x=payload.get("x"), y=payload.get("y"), x2=payload.get("x2"), y2=payload.get("y2"), source_element=payload.get("source_element") or selector, target_element=payload.get("target_element")))
        elif event_type == "open_app":
            handle_res(await DesktopController.execute(action=tool_action, app_name=payload.get("app_name") or payload.get("text")))
        elif event_type == "applescript":
            handle_res(await DesktopController.execute(action=tool_action, script=payload.get("script")))
        elif event_type == "screenshot":
            handle_res(await DesktopController.execute(action=tool_action, region=payload.get("region")))
        elif event_type == "get_active_app":
            handle_res(await DesktopController.execute(action=tool_action))
        elif event_type == "get_info":
            handle_res(await DesktopController.execute(action=tool_action, app_name=payload.get("app_name")))
        elif event_type == "dump_ui":
            handle_res(await DesktopController.execute(action=tool_action))

    @classmethod
    async def _execute_mobile_step(cls, event_type: str, selector: str, payload: dict, disable_ocr: bool = True, expected_pkg: str | None = None):
        """Execute a mobile step directly via MobileController (no @evoloop_tool overhead)."""

        from app.core.environment.controllers import MobileController

        # Normalize event_type to lowercase for case-insensitive comparison
        event_type = event_type.lower() if event_type else event_type
        tool_action = ActionRegistry.get_tool_action(event_type, "mobile")

        def handle_res(res):
            if res and isinstance(res, str):
                if "Error:" in res or "Execution failed:" in res or res.startswith("ERR_"):
                    raise ValueError(res)

        # Helper to extract x, y from various possible payload locations
        def _get_coords(p, key):
            val = p.get(key)
            if val is not None:
                return val

            # Map x->start_x, x2->end_x to handle LLM variations
            # [DEBOUNCE] Also map x2->end_x, y2->end_y for debounced swipe events
            alias_map = {
                "x": "start_x",
                "y": "start_y",
                "x2": "end_x",
                "y2": "end_y",
                "end_x": "x2",  # Reverse mapping for debounced swipe events
                "end_y": "y2"
            }
            if key in alias_map and alias_map[key] in p:
                return p[alias_map[key]]

            # [DEBOUNCE] Direct support for debounced swipe event format
            if key == "x2" and "end_x" in p:
                return p["end_x"]
            if key == "y2" and "end_y" in p:
                return p["end_y"]

            if "relative_position" in p:
                # relative_position usually only handles a single point,
                # but if swipe used it for the start, it map x, y
                if key in ["x", "y"] and key in p["relative_position"]:
                    return p["relative_position"][key]

            if "position" in p:
                if key in ["x", "y"] and key in p["position"]:
                    return p["position"][key]

            # Handle start_relative / end_relative creative LLM mapping
            if "start_relative" in p and key in ["x", "y"]:
                return p["start_relative"].get(key)
            if "end_relative" in p and key in ["x2", "y2"]:
                # Map x2 -> x inside end_relative
                return p["end_relative"].get("x" if key == "x2" else "y")

            return None

        if event_type in ("click", "tap"):
            logger.info("[_execute_mobile_step] Branch: click/tap")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            # If coordinates provided, use them directly without element resolution
            if x is not None and y is not None:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=None, timeout=payload.get("timeout", 8.0), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
            else:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=selector or payload.get("element_name") or payload.get("target"), timeout=payload.get("timeout", 8.0), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "long_press":
            logger.info("[_execute_mobile_step] Branch: long_press")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            # If coordinates provided, use them directly without element resolution
            if x is not None and y is not None:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=None, duration_ms=payload.get("duration_ms", 800), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
            else:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=selector or payload.get("element_name"), duration_ms=payload.get("duration_ms", 800), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type in ("input", "type_text"):
            handle_res(await MobileController.execute(action="input_text", text=payload.get("text") or payload.get("value", ""), element_name=selector or payload.get("element_name"), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type in ("swipe", "scroll"):
            actual_action = tool_action
            # If it's a swipe but we only have direction/distance (no coords), redirect to scroll
            if event_type == "swipe" and payload.get("direction") and _get_coords(payload, "x") is None:
                actual_action = "scroll"

            handle_res(await MobileController.execute(
                action=actual_action,
                x=_get_coords(payload, "x"),
                y=_get_coords(payload, "y"),
                x2=_get_coords(payload, "x2"),
                y2=_get_coords(payload, "y2"),
                direction=payload.get("direction"),
                scroll_amount=payload.get("distance") or payload.get("scroll_amount", "medium"),
                duration_ms=payload.get("duration_ms", 500),
                disable_atlas=True,
                disable_trace_screenshot=True,
                disable_ocr=disable_ocr,
                fast_probe=True,
                passive_safety=True
            ))
        elif event_type == "back":
            handle_res(await MobileController.execute(action="press_key", keycode="back", disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "back_key":
            handle_res(await MobileController.execute(action="press_key", keycode=payload.get("keycode", "back"), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "home":
            handle_res(await MobileController.execute(action="press_key", keycode="home", disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "key_press":
            handle_res(await MobileController.execute(action=tool_action, keycode=payload.get("key") or payload.get("keycode"), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "open_app":
            handle_res(await MobileController.execute(
                action=tool_action,
                text=payload.get("package_name") or payload.get("package") or payload.get("text") or payload.get("app_name"),
                force_stop=payload.get("force_stop", True),
                disable_atlas=True,
                disable_trace_screenshot=True,
                disable_ocr=disable_ocr,
                fast_probe=True,
                passive_safety=True
            ))
        elif event_type == "screenshot":
            handle_res(await MobileController.execute(action=tool_action, disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "dump_ui":
            handle_res(await MobileController.execute(action=tool_action, disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True, compressed_dump=False))
        elif event_type == "wait":
            duration = payload.get("seconds") or (payload.get("duration_ms", 1000) / 1000.0)
            await asyncio.sleep(float(duration))
        elif event_type == "get_clipboard":
            handle_res(await MobileController.execute(action="get_clipboard", disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "scroll_to_bottom":
            handle_res(await MobileController.execute(
                action="scroll_to_bottom",
                max_scrolls=payload.get("max_scrolls", 5),
                scroll_amount=payload.get("scroll_amount", "medium"),
                delay_ms=payload.get("delay_ms", 1000),
                disable_atlas=True,
                disable_trace_screenshot=True,
                disable_ocr=disable_ocr,
                fast_probe=True,
                passive_safety=True,
                compressed_dump=False
            ))

    # --- Utils ---
    @classmethod
    def _inject_params(cls, value: str | None, params: dict | None) -> str | None:
        if not value or not params: return value

        def _get_nested(data: dict, path: str):
            parts = path.split('.')
            curr = data
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                else:
                    return None
            return curr

        # Regex to match {{key}}, {{parameters.key}}, {{item.selector}} etc.
        pattern = r"\{\{\s*(?:parameters\.)?([a-zA-Z0-9_\-\.]+)\s*\}\}"

        def replacer(match):
            path = match.group(1)
            val = _get_nested(params, path)
            if val is not None:
                return str(val)
            return match.group(0)

        return re.sub(pattern, replacer, value)

    @classmethod
    def _inject_payload_params(cls, payload: Any, params: dict | None) -> Any:
        if not params:
            return payload
        if isinstance(payload, str):
            return cls._inject_params(payload, params)
        elif isinstance(payload, dict):
            return {k: cls._inject_payload_params(v, params) for k, v in payload.items()}
        elif isinstance(payload, list):
            return [cls._inject_payload_params(item, params) for item in payload]
        return payload
