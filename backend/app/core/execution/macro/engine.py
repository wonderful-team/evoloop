import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.environment.controllers.browser_controller import BrowserController
from app.core.environment.controllers.mobile_controller import MobileController
from app.core.environment.controllers.desktop_controller import DesktopController
from app.core.monitoring.activity import activity_monitor
from app.core.execution.macro.schema import MacroStep, MacroStepType, MacroSource
from app.core.environment.capabilities.registry import ActionRegistry

logger = logging.getLogger(__name__)


class MacroEngine:
    """
    Standardized Macro Executer for Learned Skills.
    Interprets MacroScript models and executes them against domain tools.
    """

    @classmethod
    async def execute_steps(
        cls, 
        thread_id: str, 
        steps: List[MacroStep], 
        params: Optional[Dict[str, Any]] = None, 
        extracted_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Internal recursive execution of macro steps.
        Returns (success, message, fallback_context).
        """
        if extracted_data is None:
            extracted_data = {}

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
                desc += f"(items_key='{payload.get('items_key')}')"
            elif step.type == MacroStepType.EXTRACT:
                desc += f"(key='{step.key}')"
                
            await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
            logger.info(f"[{thread_id}] {desc}")

            # 2. Handle Control Flow
            if step.type in (MacroStepType.CONTROL, MacroStepType.IF, MacroStepType.LOOP):
                success, msg, fallback = await cls._handle_control_flow(
                    thread_id, step, params, extracted_data
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

            # 5. Handle UI Action
            if step.type == MacroStepType.ACTION:
                event_type = step.event_type
                source = step.source
                
                try:
                    if source == MacroSource.DOM:
                        await cls._execute_browser_step(event_type, target_selector, payload)
                    elif source == MacroSource.MOBILE:
                        await cls._execute_mobile_step(event_type, target_selector, payload)
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
                            # Use 'debug' purpose which exists in ScreenshotPurpose enum
                            res = await BrowserController.execute(action="screenshot", purpose="debug")
                            match = re.search(r"(/.*\.png)", str(res))
                            screenshot_path = match.group(1) if match else None
                    except Exception as se:
                        logger.error(f"Failed to capture failure screenshot: {se}")

                    fallback_context = {
                        "failed_step": step.model_copy().dict(),
                        "error_message": error_msg,
                        "source": source,
                        "screenshot": screenshot_path
                    }
                    
                    if screenshot_path:
                        await activity_monitor.log_event("macro_thought", {
                            "text": f"❌ Step {step_num} failed. Failure captured: {screenshot_path}"
                        }, thread_id)
                        logger.error(f"[{thread_id}] ❌ Macro Step {step_num} failed. Screenshot: {screenshot_path}")
                    
                    return False, f"Step {step_num} failed: {error_msg}", fallback_context

                await activity_monitor.check_cancellation(thread_id)
                # Increase delay between steps for better stability
                await asyncio.sleep(1.0)
                
        return True, "", None

    @classmethod
    async def _handle_control_flow(cls, thread_id: str, step: MacroStep, params: dict, extracted_data: dict):
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
                return await cls.execute_steps(thread_id, branch, params, extracted_data)
        
        elif step.type == MacroStepType.LOOP:
            # 1. Batch Loop Mode (if payload contains items_key)
            if step.payload.get("items_key"):
                return await cls._handle_loop(thread_id, step, params, extracted_data)

            # 2. Conditional Loop Mode (Standard While)
            iterations = 0
            if not step.steps:
                return True, "", None

            while iterations < step.max_iterations:
                is_true = await cls._evaluate_condition(cond_type, selector, step.source)
                if not is_true:
                    break
                    
                loop_params = dict(params) if params else {}
                loop_params["loop_index"] = iterations
                
                # Execute nested steps
                success, msg, fallback = await cls.execute_steps(thread_id, step.steps, loop_params, extracted_data)
                
                if not success:
                    # Enrich fallback with loop progress
                    if not fallback: 
                        fallback = {"failed_step": step.model_copy().dict()}
                    
                    fallback["loop_progress"] = {
                        "loop_step_number": step.step_number,
                        "current_iteration": iterations,
                        "max_iterations": step.max_iterations,
                        "condition": cond_type
                    }
                    return False, msg, fallback
                    
                iterations += 1
            
            if iterations >= step.max_iterations:
                logger.warning(f"[{thread_id}] While loop reached max iterations ({step.max_iterations})")
                
        return True, "", None

    @classmethod
    async def _handle_loop(cls, thread_id: str, step: MacroStep, params: dict, extracted_data: dict):
        """
        Handle a batch loop by iterating over a list of items and executing nested steps.
        Includes exponential backoff for network errors and DLQ support.
        Phase 3: Integrates DynamicAppTriage for autonomous scrolling.
        """
        items_key = step.payload.get("items_key", "items")
        items = extracted_data.get(items_key) or params.get(items_key)
        
        if not items or not isinstance(items, list):
            warn_msg = f"⚠️ Batch loop skipped: No items found for key '{items_key}'"
            logger.warning(f"[{thread_id}] {warn_msg}")
            await activity_monitor.log_event("macro_thought", {"text": warn_msg}, thread_id)
            return True, "", None

        logger.info(f"[{thread_id}] 🔄 Starting Batch Loop: {len(items)} items for key '{items_key}'")
        await activity_monitor.log_event("macro_thought", {"text": f"🔄 Starting loop ({len(items)} items)"}, thread_id)

        # Phase 3: Dynamic App Awareness
        is_dynamic = False
        bundle_id = None
        if step.source == MacroSource.MOBILE:
            try:
                from app.infrastructure.drivers.adb import adb_driver
                from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
                from app.core.context.manager import ContextManager
                
                device_id = ContextManager.get_var("device_id")
                curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                bundle_id = curr_app.get("package")
                if bundle_id:
                    dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform="android")
                    is_dynamic = bundle_id in dynamic_apps
                    if is_dynamic:
                        logger.info(f"[{thread_id}] LOOP running on DYNAMIC app: {bundle_id}. Enabling autonomous scrolling.")
            except Exception as e:
                logger.warning(f"Failed to detect dynamic status: {e}")

        max_retries = step.payload.get("max_retries", 3)
        backoff_base = step.payload.get("backoff_base", 2)
        
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
                    success, msg, fallback = await cls.execute_steps(thread_id, step.steps, iter_params, extracted_data)
                    
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
    async def _evaluate_condition(cls, cond_type: str, selector: str, source: str) -> bool:
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

        return False

    @classmethod
    async def _handle_extraction(cls, thread_id: str, step: MacroStep, selector: str, payload: dict, params: dict, extracted_data: dict):
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

        elif step.source in (MacroSource.MOBILE, MacroSource.GLOBAL):
            if extract_type == "dump_ui":
                res = await MobileController.execute(action="dump_ui")
                extracted_data[key] = res
            elif extract_type == "screenshot":
                res = await MobileController.execute(action="screenshot")
                match = re.search(r"(/.*\.png)", str(res))
                filepath = match.group(1) if match else str(res)
                if selector and filepath.endswith(".png"):
                    filepath = await cls._crop_mobile_screenshot(filepath, selector)
                extracted_data[key] = filepath

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
        sink_path = payload.get("path", f"/tmp/macro_results_{thread_id}.json")
        await activity_monitor.log_event("macro_thought", {"text": f"Dump extracted data to {sink_path}"}, thread_id)
        try:
            with open(sink_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to dump data: {e}")

    # --- Tool Invocation Wrappers (Browser/Mobile/Desktop) ---

    @classmethod
    async def _execute_browser_step(cls, event_type: str, selector: str, payload: dict):
        """Execute a browser step directly via BrowserController (no @evoloop_tool overhead)."""
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
    async def _execute_mobile_step(cls, event_type: str, selector: str, payload: dict):
        """Execute a mobile step directly via MobileController (no @evoloop_tool overhead)."""
        tool_action = ActionRegistry.get_tool_action(event_type, "mobile")

        if event_type in ("click", "tap"):
            await MobileController.execute(action=tool_action, x=payload.get("x"), y=payload.get("y"), element_name=selector or payload.get("element_name") or payload.get("target"), timeout=payload.get("timeout", 8.0))
        elif event_type == "long_press":
            await MobileController.execute(action=tool_action, x=payload.get("x"), y=payload.get("y"), element_name=selector or payload.get("element_name"), duration_ms=payload.get("duration_ms", 800))
        elif event_type in ("input", "type_text"):
            await MobileController.execute(action="input_text", text=payload.get("text") or payload.get("value", ""), element_name=selector or payload.get("element_name"))
        elif event_type in ("swipe", "scroll"):
            await MobileController.execute(action=tool_action, x=payload.get("x"), y=payload.get("y"), x2=payload.get("x2"), y2=payload.get("y2"), direction=payload.get("direction"), duration_ms=payload.get("duration_ms", 500))
        elif event_type == "back":
            await MobileController.execute(action="press_key", keycode="back")
        elif event_type == "back_key":
            await MobileController.execute(action="press_key", keycode=payload.get("keycode", "back"))
        elif event_type == "home":
            await MobileController.execute(action="press_key", keycode="home")
        elif event_type == "key_press":
            await MobileController.execute(action=tool_action, keycode=payload.get("key") or payload.get("keycode"))
        elif event_type == "open_app":
            await MobileController.execute(action=tool_action, text=payload.get("package") or payload.get("text") or payload.get("app_name"))
        elif event_type == "screenshot":
            await MobileController.execute(action=tool_action)
        elif event_type == "dump_ui":
            await MobileController.execute(action=tool_action)

    # --- Utils ---
    @classmethod
    def _inject_params(cls, value: Optional[str], params: Optional[dict]) -> Optional[str]:
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
    def _inject_payload_params(cls, payload: Any, params: Optional[dict]) -> Any:
        if not params: return payload
        if isinstance(payload, str):
            return cls._inject_params(payload, params)
        elif isinstance(payload, dict):
            return {k: cls._inject_payload_params(v, params) for k, v in payload.items()}
        elif isinstance(payload, list):
            return [cls._inject_payload_params(item, params) for item in payload]
        return payload
