import asyncio
import logging
from typing import Any

from app.domain.tools.environment.browser import browser_control
from app.domain.tools.environment.mobile import mobile_control
from app.domain.tools.environment.desktop import desktop_control
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


class MacroEngine:
    """
    Deterministic Macro Executer for Learned Skills.
    Takes a pre-compiled JSON script of trace events and executes them
    directly against the domain environment tools, bypassing the Agentic LLM layer.
    """

    @classmethod
    async def execute(cls, thread_id: str, macro_script: list[dict], params: dict[str, Any] = None):
        """
        Execute a macro sequence and report progress.
        """
        if not macro_script:
            logger.warning(f"[{thread_id}] Macro execution skipped: macro_script is empty.")
            return {"success": False, "message": "Macro script is empty"}

        logger.info(f"[{thread_id}] Starting Deterministic Macro Execution ({len(macro_script)} steps)")
        
        # Start a run in the activity monitor so it shows up in UI
        await activity_monitor.start_run(thread_id)
        
        extracted_data = {}
        
        try:
            success, msg, fallback_ctx = await cls._run_steps(thread_id, macro_script, params, extracted_data)
            
            if not success:
                logger.error(f"[{thread_id}] Macro failed: {msg}")
                await activity_monitor.end_run(thread_id, "failed")
                result_payload = {"success": False, "message": msg}
                if fallback_ctx:
                    result_payload["status"] = "fallback_required"
                    result_payload["fallback_context"] = fallback_ctx
                return result_payload

            # Execution Finished
            await activity_monitor.log_event("macro_thought", {"text": "Macro execution completed successfully."}, thread_id)
            await activity_monitor.end_run(thread_id, "done")
            return {"success": True, "message": "Deterministic Macro Execution Complete.", "extracted_data": extracted_data}

        except Exception as e:
            logger.error(f"[{thread_id}] Macro execution error: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, "failed")
            return {"success": False, "message": f"Execution failed: {str(e)}"}

    @classmethod
    async def _run_steps(cls, thread_id: str, steps: list[dict], params: dict, extracted_data: dict) -> tuple[bool, str, dict | None]:
        for i, step in enumerate(steps):
            step_num = step.get("step_number", i + 1)
            action_type = step.get("type", "action")
            
            target_selector = cls._inject_params(step.get("target_selector"), params)
            payload = step.get("payload", {})
            for k, v in payload.items():
                if isinstance(v, str):
                    payload[k] = cls._inject_params(v, params)
                    
            # Fallback for LLM-generated tool traces where selector is buried in the payload kwargs
            target_selector = target_selector or payload.get("selector")

            if action_type == "if":
                condition = step.get("condition", {})
                cond_type = condition.get("type")
                selector = condition.get("target_selector")
                
                desc = f"Evaluate Condition: {cond_type} on {selector}"
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                logger.debug(f"[{thread_id}] {desc}")
                
                is_true = False
                if cond_type == "element_exists":
                    source = step.get("source", "dom")
                    if source == "dom":
                        res = await browser_control.ainvoke({"action": "check_element", "selector": selector})
                        if "visible=True" in str(res):
                            is_true = True
                    elif source in ("mobile", "global"):
                        res = await mobile_control.ainvoke({"action": "dump_ui"})
                        if selector in str(res):
                            is_true = True
                    elif source == "desktop":
                        # Desktop: 使用 applescript 检查元素存在性
                        res = await desktop_control.ainvoke({"action": "applescript", "script": f'tell application "System Events" to exists (first UI element whose name contains "{selector}")'})
                        if "true" in str(res).lower():
                            is_true = True
                
                branch = step.get("then", []) if is_true else step.get("else", [])
                if branch:
                    success, msg, fallback_ctx = await cls._run_steps(thread_id, branch, params, extracted_data)
                    if not success:
                        return False, msg, fallback_ctx

            elif action_type == "while":
                condition = step.get("condition", {})
                cond_type = condition.get("type")
                selector = condition.get("target_selector")
                
                desc = f"Evaluate Loop Condition: {cond_type} on {selector}"
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                logger.debug(f"[{thread_id}] {desc}")
                
                max_iterations = step.get("max_iterations", 100)
                iterations = 0
                
                while iterations < max_iterations:
                    is_true = False
                    if cond_type == "element_exists":
                        source = step.get("source", "dom")
                        if source == "dom":
                            res = await browser_control.ainvoke({"action": "check_element", "selector": selector})
                            if "visible=True" in str(res):
                                is_true = True
                        elif source in ("mobile", "global"):
                            res = await mobile_control.ainvoke({"action": "dump_ui"})
                            if selector in str(res):
                                is_true = True
                        elif source == "desktop":
                            res = await desktop_control.ainvoke({"action": "applescript", "script": f'tell application "System Events" to exists (first UI element whose name contains "{selector}")'})
                            if "true" in str(res).lower():
                                is_true = True

                    if not is_true:
                        break
                        
                    body = step.get("do", [])
                    if body:
                        loop_params = dict(params) if params else {}
                        loop_params["loop_index"] = iterations
                        success, msg, fallback_ctx = await cls._run_steps(thread_id, body, loop_params, extracted_data)
                        if not success:
                            return False, msg, fallback_ctx
                    
                    iterations += 1
                
                if iterations >= max_iterations:
                    logger.warning(f"[{thread_id}] While loop reached max iterations ({max_iterations})")

            elif action_type == "extract":
                source = step.get("source", "dom")
                key = step.get("key", "data")
                key = cls._inject_params(key, params) or key
                extract_type = step.get("extract_type", "get_text")
                
                desc = f"Extract '{key}' from {target_selector}"
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                
                if source == "dom":
                    call_params = {"action": extract_type, "selector": target_selector}
                    if extract_type == "get_attribute" and "attribute" in payload:
                        call_params["attribute"] = payload["attribute"]
                    if extract_type == "run_js" and "script" in payload:
                        call_params["script"] = payload["script"]
                    elif extract_type == "evaluate" and "expression" in payload:
                        # Map evaluate to run_js for convenience
                        call_params["action"] = "run_js"
                        call_params["script"] = payload["expression"]
                        
                    res = await browser_control.ainvoke(call_params)
                    if extract_type == "screenshot":
                        import re
                        match = re.search(r"(/.*\.png)", str(res))
                        extracted_data[key] = match.group(1) if match else res
                    else:
                        extracted_data[key] = res
                elif source in ("mobile", "global"):
                    if extract_type == "dump_ui":
                        res = await mobile_control.ainvoke({"action": "dump_ui"})
                        extracted_data[key] = res
                    elif extract_type == "screenshot":
                        # Support focused screenshots on mobile within the Macro Engine
                        res = await mobile_control.ainvoke({"action": "screenshot"})
                        import re
                        match = re.search(r"(/.*\.png)", str(res))
                        filepath = match.group(1) if match else str(res)
                        
                        if target_selector and filepath.endswith(".png"):
                            try:
                                from PIL import Image
                                from app.core.vision.providers.native.android_a11y import android_a11y_provider
                                from app.core.vision.types import VisionTask
                                import os
                                
                                def _norm(t): return re.sub(r'\s+', '', t).lower() if t else ""
                                
                                a11y_res = await android_a11y_provider.process(VisionTask.DETECT, "", device_id=None)
                                target_bounds = None
                                if a11y_res.success:
                                    target_norm = _norm(target_selector)
                                    for el in a11y_res.elements:
                                        if _norm(el.text) == target_norm or target_norm in _norm(el.metadata.get("resource_id", "")):
                                            target_bounds = (el.x - el.width//2, el.y - el.height//2, el.x + el.width//2, el.y + el.height//2)
                                            break
                                            
                                if target_bounds:
                                    with Image.open(filepath) as img:
                                        cropped = img.crop(target_bounds)
                                        safe_name = _norm(target_selector)[:15]
                                        filepath_cropped = filepath.replace(".png", f"_crop_{safe_name}.png")
                                        cropped.save(filepath_cropped)
                                        try: os.remove(filepath)
                                        except: pass
                                        filepath = filepath_cropped
                                        logger.info(f"[{thread_id}] MacroEngine cropped screenshot for '{target_selector}' to {filepath}")
                            except Exception as e:
                                logger.warning(f"[{thread_id}] MacroEngine cropping failed: {e}")
                                
                        extracted_data[key] = filepath

            elif action_type == "dump":
                sink_path = payload.get("path", f"/tmp/macro_results_{thread_id}.json")
                desc = f"Dump extracted data to {sink_path}"
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                
                import json
                try:
                    with open(sink_path, "w", encoding="utf-8") as f:
                        json.dump(extracted_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to dump data to {sink_path}: {e}")

            else:
                event_type = step.get("event_type")
                source = step.get("source", "dom")

                # if event_type in ["tool_call", "tool_result", "macro_thought"]:
                #     continue

                desc = f"Execute Macro Step {step_num}: {event_type} "
                if target_selector:
                    desc += f"on {target_selector}"
                elif "url" in payload:
                    desc += f"to {payload['url']}"
                    
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
                logger.debug(f"[{thread_id}] {desc}")
                
                error_msg = None
                fallback_context = None
                try:
                    if source == "dom":
                        await cls._execute_browser_step(event_type, target_selector, payload)
                    elif source == "mobile":
                        await cls._execute_mobile_step(event_type, target_selector, payload)
                    elif source == "desktop":
                        await cls._execute_desktop_step(event_type, target_selector, payload)
                    else:
                        logger.warning(f"Unknown macro source: {source}")
                except Exception as e:
                    error_msg = str(e)
                    fallback_context = {
                        "failed_step": step,
                        "error_message": error_msg,
                        "source": source
                    }

                await activity_monitor.check_cancellation(thread_id)
                
                if error_msg:
                    return False, f"Step {step_num} failed: {error_msg}", fallback_context
                    
                await asyncio.sleep(0.5)
                
        return True, "", None

    @classmethod
    async def _execute_browser_step(cls, event_type: str, selector: str | None, payload: dict):
        """Map generic trace events to browser_control tool actions"""
        # browser_control is an evoloop_tool, which wraps 'ainvoke'
        
        # When an Agent generates the step (tool_call), the selector is inside the payload
        selector = selector or payload.get("selector")
        
        # Extract global modifiers
        continue_on_error = payload.get("continue_on_error", False)
        timeout_ms = payload.get("timeout_ms", 15000)
        
        def handle_res(res):
            if res and isinstance(res, str):
                if res.startswith("Warning:"):
                    logger.warning(f"MacroEngine Optional Step Warning: {res}")
                elif "Execution failed:" in res or "Error:" in res:
                    if continue_on_error:
                        logger.warning(f"Optional step failed (continue_on_error=True): {res}")
                    else:
                        raise ValueError(res)
                    
        # Apply global modifiers to browser params
        base_params = {"timeout_ms": timeout_ms}
        
        if event_type in ["goto", "navigate"]:
            url = payload.get("url")
            res = await browser_control.ainvoke({"action": "navigate", "url": url, **base_params})
            handle_res(res)
            # Wait for dynamic SPAs to settle
            await asyncio.sleep(2)
            
        elif event_type == "click":
            # For robustness in headless playback, we attempt standard click, 
            # and may need to inject force=True logic. Our domain tool handles basic clicks natively.
            res = await browser_control.ainvoke({
                "action": "click", 
                "selector": selector,
                **base_params
            })
            handle_res(res)
            
        elif event_type in ["input", "fill"]:
            text = payload.get("text") or payload.get("value", "")
            res = await browser_control.ainvoke({
                "action": "type_text",
                "selector": selector,
                "value": text,
                "clear_first": True,
                **base_params
            })
            handle_res(res)

        elif event_type == "key_press":
            key = payload.get("key")
            if key:
                res = await browser_control.ainvoke({
                    "action": "key_press",
                    "key": key,
                    **base_params
                })
                handle_res(res)

        elif event_type == "wait":
            if "seconds" in payload:
                duration = float(payload.get("seconds"))
            else:
                duration = payload.get("duration_ms", 1000) / 1000.0
            await asyncio.sleep(duration)

        elif event_type == "wait_for":
            selector = payload.get("selector")
            state = payload.get("state", "visible")
            res = await browser_control.ainvoke({
                "action": "wait_for",
                "selector": selector,
                "state": state,
                **base_params
            })
            handle_res(res)

        elif event_type == "scroll":
            res = await browser_control.ainvoke({
                "action": "scroll",
                "direction": payload.get("direction", "down"),
                "amount": payload.get("amount", 300)
            })
            handle_res(res)
            
        elif event_type == "run_js":
            script = payload.get("script")
            if script:
                res = await browser_control.ainvoke({"action": "run_js", "script": script})
                handle_res(res)
                
        elif event_type == "screenshot":
            res = await browser_control.ainvoke({"action": "screenshot", "ocr": payload.get("ocr", False)})
            handle_res(res)
            
        elif event_type == "get_url":
            res = await browser_control.ainvoke({"action": "get_url"})
            handle_res(res)
            
        elif event_type in ["tool_call", "tool_result", "macro_thought"]:
            # Silently skip agentic noise that might leak into the script
            return
            
        else:
            logger.warning(f"MacroEngine: Unsupported browser event type: {event_type}")

    @classmethod
    async def _execute_desktop_step(cls, event_type: str, selector: str | None, payload: dict):
        """Map generic events to desktop_control actions (MacOS)"""
        
        # Consistent target resolution
        selector = selector or payload.get("element_name") or payload.get("target")

        if event_type in ["click", "double_click"]:
            res = await desktop_control.ainvoke({
                "action": event_type,
                "element_name": selector,
                "x": payload.get("x"),
                "y": payload.get("y")
            })
            if res and isinstance(res, str) and "Error:" in res:
                raise ValueError(res)

        elif event_type in ["input", "type_text"]:
            text = payload.get("text") or payload.get("value", "")
            res = await desktop_control.ainvoke({
                "action": "type_text",
                "text": text
            })
            if res and isinstance(res, str) and "Error:" in res:
                raise ValueError(res)

        elif event_type == "key_press":
            key = payload.get("key")
            if key:
                res = await desktop_control.ainvoke({"action": "key_press", "key": key})
                if res and isinstance(res, str) and "Error:" in res:
                    raise ValueError(res)

        elif event_type == "open_app":
            app_name = payload.get("app_name") or payload.get("text")
            if app_name:
                res = await desktop_control.ainvoke({"action": "open_app", "app_name": app_name})
                if res and isinstance(res, str) and "Error:" in res:
                    raise ValueError(res)

        elif event_type == "applescript":
            script = payload.get("script")
            if script:
                res = await desktop_control.ainvoke({"action": "applescript", "script": script})
                if res and isinstance(res, str) and "Error:" in res:
                    raise ValueError(res)

        elif event_type == "scroll":
            res = await desktop_control.ainvoke({
                "action": "scroll",
                "direction": payload.get("direction", "down"),
                "amount": payload.get("amount", 300)
            })
            if res and isinstance(res, str) and "Error:" in res:
                raise ValueError(res)

        elif event_type == "wait":
            duration = payload.get("duration_ms", 1000) / 1000.0
            await asyncio.sleep(duration)

        elif event_type == "screenshot":
            res = await desktop_control.ainvoke({"action": "screenshot", "ocr": payload.get("ocr", False)})
            if res and isinstance(res, str) and "Error:" in res:
                raise ValueError(res)
        else:
            logger.warning(f"MacroEngine: Unsupported desktop event type: {event_type}")

    @classmethod
    async def _execute_mobile_step(cls, event_type: str, selector: str | None, payload: dict):
        """Map global events to mobile_control actions (if android)"""
        if event_type == "click" or event_type == "press":
            x = payload.get("x")
            y = payload.get("y")
            if x is not None and y is not None:
                await mobile_control.ainvoke({
                    "action": "tap",
                    "x": x,
                    "y": y
                })
        elif event_type == "input":
            text = payload.get("text", "")
            await mobile_control.ainvoke({
                "action": "input_text",
                "text": text
            })
        elif event_type in ["swipe", "scroll"]:
            res = await mobile_control.ainvoke({
                "action": "swipe",
                "x": payload.get("x"),
                "y": payload.get("y"),
                "x2": payload.get("x2"),
                "y2": payload.get("y2"),
                "duration_ms": payload.get("duration_ms", 500)
            })
        elif event_type == "open_app":
            app_name = payload.get("app_name") or payload.get("text")
            if app_name:
                await mobile_control.ainvoke({"action": "open_app", "text": app_name})
        elif event_type == "long_press":
            await mobile_control.ainvoke({
                "action": "long_press",
                "x": payload.get("x"),
                "y": payload.get("y"),
                "element_name": selector or payload.get("element_name"),
                "duration_ms": payload.get("duration_ms", 1000)
            })
        elif event_type == "screenshot":
            res = await mobile_control.ainvoke({"action": "screenshot"})
            return res
        elif event_type == "tap":
            x = payload.get("x")
            y = payload.get("y")
            await mobile_control.ainvoke({"action": "tap", "x": x, "y": y})
        elif event_type == "wait":
            duration = payload.get("duration_ms", 1000) / 1000.0
            await asyncio.sleep(duration)
        elif event_type == "wait_for":
            selector = payload.get("selector")
            timeout_ms = payload.get("timeout_ms", 15000)
            import time
            start = time.time()
            found = False
            while (time.time() - start) * 1000 < timeout_ms:
                res = await mobile_control.ainvoke({"action": "dump_ui"})
                if selector in str(res):  # Basic text/content existence check
                    found = True
                    break
                await asyncio.sleep(1)
            if not found:
                raise ValueError(f"Timeout waiting for mobile element: {selector}")
        else:
            logger.warning(f"MacroEngine: Unsupported mobile event type: {event_type}")

    @classmethod
    def _inject_params(cls, value: str | None, params: dict | None) -> str | None:
        """Replace {{param.name}} inside string with actual value"""
        if not value or not params:
            return value
        
        # Super simple injection
        import re
        result = value
        for k, v in params.items():
            pattern = r"\{\{\s*(parameters\.)?" + re.escape(k) + r"\s*\}\}"
            result = re.sub(pattern, str(v), result)
        return result
