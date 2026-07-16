import asyncio
import logging

from app.core.environment.capabilities.registry import ActionRegistry

logger = logging.getLogger(__name__)


class ExecutorMixin:
    @classmethod
    async def _execute_browser_step(cls, event_type, selector, payload):
        from app.core.environment.controllers import BrowserController

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
            target_url = payload.get("url")
            # Navigation skip: when the browser already sits on the exact
            # target URL (query string included — ?goods_id=2 vs 3 must NOT
            # skip), goto is pure waste (~2s per multi-turn step).
            from app.infrastructure.drivers.browser import browser_manager

            page = await browser_manager.get_page()
            if page is not None and isinstance(target_url, str) and page.url.rstrip("/") == target_url.rstrip("/"):
                logger.info("[macro-engine] navigate skip: already on %s", target_url)
                return
            res = await BrowserController.execute(action=tool_action, url=target_url, timeout_ms=timeout_ms, continue_on_error=continue_on_error)
            handle_res(res)
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
    async def _execute_desktop_step(cls, event_type, selector, payload):
        from app.core.environment.controllers import DesktopController

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
            bundle_id = payload.get("bundle_id")
            if bundle_id and payload.get("focus") is False:
                # Focus-free launch (Atlas-Native): open -b + window poll.
                from app.core.atlas.ax_actions import ensure_pid

                pid = await asyncio.to_thread(ensure_pid, bundle_id)
                if pid is None:
                    raise ValueError(f"Error: open_app failed for {bundle_id}")
            else:
                handle_res(await DesktopController.execute(action=tool_action, app_name=payload.get("app_name") or payload.get("text")))
        elif event_type == "ax_press":
            from app.core.atlas.ax_actions import (
                activate_at_path,
                ensure_pid,
                perform_by_label,
                press_at_path,
            )

            pid = await asyncio.to_thread(ensure_pid, payload["bundle_id"])
            if pid is None:
                raise ValueError(f"Error: app not running: {payload['bundle_id']}")
            ax_action = payload.get("ax_action")
            # 优先 role+label 运行时解析，ax_path 兜底
            if payload.get("role") and payload.get("label") and ax_action:
                ok = await asyncio.to_thread(perform_by_label, pid, payload["role"], payload["label"], ax_action)
                if ok:
                    return
            if ax_action:
                ok = await asyncio.to_thread(press_at_path, pid, payload["ax_path"], ax_action)
            else:
                ok = await asyncio.to_thread(activate_at_path, pid, payload["ax_path"])
            if not ok:
                raise ValueError(f"Error: ax_press failed at {payload['ax_path']}")
        elif event_type == "ax_menu_press":
            from app.core.atlas.ax_actions import ensure_pid, press_menu_labels

            pid = await asyncio.to_thread(ensure_pid, payload["bundle_id"])
            if pid is None:
                raise ValueError(f"Error: app not running: {payload['bundle_id']}")
            labels = payload.get("menu_labels") or []
            ok = await asyncio.to_thread(press_menu_labels, pid, labels)
            if not ok:
                raise ValueError(f"Error: ax_menu_press failed: {' > '.join(labels)}")
        elif event_type == "ax_set_value":
            from app.core.atlas.ax_actions import (
                ensure_pid,
                set_value_at_path,
                set_value_by_label,
            )

            pid = await asyncio.to_thread(ensure_pid, payload["bundle_id"])
            if pid is None:
                raise ValueError(f"Error: app not running: {payload['bundle_id']}")
            text = payload.get("text") or payload.get("value", "")
            # 优先 role+label 运行时解析（结构路径会随 UI 演化失效），ax_path 兜底
            if payload.get("role") and payload.get("label"):
                ok = await asyncio.to_thread(set_value_by_label, pid, payload["role"], payload["label"], text)
            else:
                ok = False
            if not ok and payload.get("ax_path"):
                ok = await asyncio.to_thread(set_value_at_path, pid, payload["ax_path"], text)
            if not ok:
                raise ValueError(f"Error: ax_set_value rejected for {payload.get('label') or payload.get('ax_path')}")
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
    async def _execute_mobile_step(cls, event_type, selector, payload, disable_ocr=True, expected_pkg=None):
        from app.core.environment.controllers import MobileController

        event_type = event_type.lower() if event_type else event_type
        tool_action = ActionRegistry.get_tool_action(event_type, "mobile")

        def handle_res(res):
            if res and isinstance(res, str):
                if "Error:" in res or "Execution failed:" in res or res.startswith("ERR_"):
                    raise ValueError(res)

        def _get_coords(p, key):
            val = p.get(key)
            if val is not None:
                return val

            alias_map = {
                "x": "start_x", "y": "start_y",
                "x2": "end_x", "y2": "end_y",
                "end_x": "x2", "end_y": "y2"
            }
            if key in alias_map and alias_map[key] in p:
                return p[alias_map[key]]

            if key == "x2" and "end_x" in p:
                return p["end_x"]
            if key == "y2" and "end_y" in p:
                return p["end_y"]

            if "relative_position" in p:
                if key in ["x", "y"] and key in p["relative_position"]:
                    return p["relative_position"][key]

            if "position" in p:
                if key in ["x", "y"] and key in p["position"]:
                    return p["position"][key]

            if "start_relative" in p and key in ["x", "y"]:
                return p["start_relative"].get(key)
            if "end_relative" in p and key in ["x2", "y2"]:
                return p["end_relative"].get("x" if key == "x2" else "y")

            return None

        if event_type in ("click", "tap"):
            logger.info("[_execute_mobile_step] Branch: click/tap")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            if x is not None and y is not None:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=None, timeout=payload.get("timeout", 8.0), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
            else:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=selector or payload.get("element_name") or payload.get("target"), timeout=payload.get("timeout", 8.0), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type == "long_press":
            logger.info("[_execute_mobile_step] Branch: long_press")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            if x is not None and y is not None:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=None, duration_ms=payload.get("duration_ms", 800), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
            else:
                handle_res(await MobileController.execute(action=tool_action, x=x, y=y, element_name=selector or payload.get("element_name"), duration_ms=payload.get("duration_ms", 800), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type in ("input", "type_text"):
            handle_res(await MobileController.execute(action="input_text", text=payload.get("text") or payload.get("value", ""), element_name=selector or payload.get("element_name"), disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True))
        elif event_type in ("swipe", "scroll"):
            actual_action = tool_action
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
                disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True
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
                disable_atlas=True, disable_trace_screenshot=True, disable_ocr=disable_ocr, fast_probe=True, passive_safety=True, compressed_dump=False
            ))
