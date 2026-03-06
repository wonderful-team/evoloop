import asyncio
import logging
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

            # 2. Handle Control Flow
            if step.type in (MacroStepType.CONTROL, MacroStepType.IF, MacroStepType.WHILE):
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

            # 5. Regular UI Action
            if step.type == MacroStepType.ACTION:
                event_type = step.event_type
                source = step.source
                
                desc = f"Execute Macro Step {step_num}: {event_type} "
                if target_selector:
                    desc += f"on {target_selector}"
                elif "url" in payload:
                    desc += f"to {payload['url']}"
                    
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                logger.debug(f"[{thread_id}] {desc}")
                
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
                    fallback_context = {
                        "failed_step": step.model_copy().dict(),
                        "error_message": error_msg,
                        "source": source
                    }
                    return False, f"Step {step_num} failed: {error_msg}", fallback_context

                await activity_monitor.check_cancellation(thread_id)
                await asyncio.sleep(0.5)
                
        return True, "", None

    @classmethod
    async def _handle_control_flow(cls, thread_id: str, step: MacroStep, params: dict, extracted_data: dict):
        # Implementation of If/While logic
        condition = step.condition
        if not condition:
            return True, "", None
            
        cond_type = condition.type
        selector = cls._inject_params(condition.target_selector, params)
        
        if step.type in (MacroStepType.CONTROL, MacroStepType.IF):
            is_true = await cls._evaluate_condition(cond_type, selector, step.source)
            branch = step.then_steps if is_true else step.else_steps
            if branch:
                return await cls.execute_steps(thread_id, branch, params, extracted_data)
        
        elif step.type == MacroStepType.WHILE:
            iterations = 0
            while iterations < step.max_iterations:
                is_true = await cls._evaluate_condition(cond_type, selector, step.source)
                if not is_true:
                    break
                    
                loop_params = dict(params) if params else {}
                loop_params["loop_index"] = iterations
                
                # Execute nested steps
                success, msg, fallback = await cls.execute_steps(thread_id, step.do_steps, loop_params, extracted_data)
                
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
            import os
            
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
        import json
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
            res = await BrowserController.execute(action=tool_action, url=payload.get("url"), timeout_ms=timeout_ms)
            handle_res(res)
            await asyncio.sleep(2)
        elif event_type == "back":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms))
        elif event_type == "forward":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms))
        elif event_type == "reload":
            handle_res(await BrowserController.execute(action=tool_action, timeout_ms=timeout_ms))
        elif event_type in ("click", "tap", "double_click", "hover"):
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, x=payload.get("x"), y=payload.get("y"), timeout_ms=timeout_ms))
        elif event_type in ("input", "type_text"):
            handle_res(await BrowserController.execute(action="type_text", selector=selector, value=payload.get("text") or payload.get("value", ""), clear_first=payload.get("clear_first", True), timeout_ms=timeout_ms))
        elif event_type == "select_option":
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, value=payload.get("value"), timeout_ms=timeout_ms))
        elif event_type == "key_press":
            handle_res(await BrowserController.execute(action=tool_action, key=payload.get("key"), timeout_ms=timeout_ms))
        elif event_type == "drag_drop":
            handle_res(await BrowserController.execute(action=tool_action, source_selector=payload.get("source_selector") or selector, target_selector=payload.get("target_selector"), timeout_ms=timeout_ms))
        elif event_type == "upload":
            handle_res(await BrowserController.execute(action=tool_action, selector=selector, file_path=payload.get("file_path"), timeout_ms=timeout_ms))
        elif event_type == "wait":
            duration = payload.get("seconds") or (payload.get("duration_ms", 1000) / 1000.0)
            await asyncio.sleep(float(duration))
        elif event_type == "wait_for":
            handle_res(await BrowserController.execute(action=tool_action, selector=payload.get("selector") or selector, state=payload.get("state", "visible"), url_pattern=payload.get("url_pattern"), timeout_ms=timeout_ms))
        elif event_type == "scroll":
            await BrowserController.execute(action=tool_action, selector=selector, direction=payload.get("direction", "down"), amount=payload.get("amount", 300))
        elif event_type == "screenshot":
            await BrowserController.execute(action=tool_action, selector=selector, full_page=payload.get("full_page", False))
        elif event_type == "new_tab":
            await BrowserController.execute(action=tool_action, url=payload.get("url"))
        elif event_type == "switch_tab":
            await BrowserController.execute(action=tool_action, tab_index=payload.get("tab_index"))
        elif event_type == "dialog_handle":
            await BrowserController.execute(action=tool_action, dialog_action=payload.get("dialog_action"), dialog_text=payload.get("dialog_text"))
        elif event_type in ("run_js", "evaluate"):
            await BrowserController.execute(action="run_js", script=payload.get("script") or payload.get("expression"))

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
        result = value
        for k, v in params.items():
            pattern = r"\{\{\s*(parameters\.)?" + re.escape(k) + r"\s*\}\}"
            result = re.sub(pattern, str(v), result)
        return result

    @classmethod
    def _inject_payload_params(cls, payload: dict, params: Optional[dict]) -> dict:
        if not params: return payload
        new_payload = dict(payload)
        for k, v in new_payload.items():
            if isinstance(v, str):
                new_payload[k] = cls._inject_params(v, params)
        return new_payload
