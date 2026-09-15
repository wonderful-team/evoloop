import asyncio
import logging

import app.core.learning.constants as _mc
from app.core.environment.capabilities.registry import ActionRegistry

logger = logging.getLogger(__name__)


def _is_false_result(res: str) -> bool:
    """Detect a run_js result that resolves to false/undefined/null.

    ``BrowserController.execute(action="run_js")`` renders the evaluate result
    as ``JS result: <value>``. We only treat explicit falsy scalars as "step
    did not succeed" so that ``true``/strings/objects keep passing.
    """
    r = res.strip().lower()
    if r in (
        "js result: false",
        "js result: null",
        "js result: undefined",
        "js result: 0",
    ):
        return True
    return any(
        m in r for m in ("js result: false", "js result: null", "js result: undefined")
    )


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
                # 统一错误识别：❌（ControllerResponse.error 渲染）也是失败信号，
                # 与 Desktop 分支对齐。宏步骤可用 continue_on_error: true 显式跳过。
                if "Execution failed:" in res or "Error:" in res or "❌" in res:
                    if not continue_on_error:
                        raise ValueError(res)

        # ── 操作前就绪等待（pre_wait）────────────────────────────
        # 允许宏声明"操作前等某元素就绪"（素材/弹窗/数据加载），wait_for 超时
        # 返回 ❌ → handle_res 抛异常停止，避免"点空/填空"后继续。
        pre_wait = payload.get("pre_wait")
        if isinstance(pre_wait, dict) and pre_wait.get("selector"):
            res = await BrowserController.execute(
                action=_mc.WAIT_FOR,
                selector=pre_wait["selector"],
                state=pre_wait.get("state", "visible"),
                timeout_ms=pre_wait.get("timeout_ms", 8000),
            )
            handle_res(res)

        tool_action = ActionRegistry.get_tool_action(event_type, _mc.DOM)

        if event_type in (_mc.GOTO, _mc.NAVIGATE):
            target_url = payload.get("url")
            # Navigation skip: when the browser already sits on the exact
            # target URL (query string included — ?goods_id=2 vs 3 must NOT
            # skip), goto is pure waste (~2s per multi-turn step).
            from app.infrastructure.drivers.browser import browser_manager

            page = await browser_manager.get_page()
            if (
                page is not None
                and isinstance(target_url, str)
                and page.url.rstrip("/") == target_url.rstrip("/")
            ):
                logger.info("[macro-engine] navigate skip: already on %s", target_url)
                return True
            res = await BrowserController.execute(
                action=tool_action,
                url=target_url,
                timeout_ms=timeout_ms,
                continue_on_error=continue_on_error,
            )
            handle_res(res)
            await BrowserController.execute(
                action="wait_for_stability", timeout_ms=5000
            )
        elif event_type == _mc.BACK:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.FORWARD:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.RELOAD:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type in (_mc.CLICK, _mc.TAP, _mc.DOUBLE_CLICK, _mc.HOVER):
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    selector=selector,
                    x=payload.get("x"),
                    y=payload.get("y"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type in (_mc.INPUT, _mc.TYPE_TEXT):
            handle_res(
                await BrowserController.execute(
                    action=_mc.TYPE_TEXT,
                    selector=selector,
                    value=payload.get("text") or payload.get("value", ""),
                    clear_first=payload.get("clear_first", True),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.SELECT_OPTION:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    selector=selector,
                    value=payload.get("value"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.KEY_PRESS:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    key=payload.get("key"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.DRAG_DROP:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    source_selector=payload.get("source_selector") or selector,
                    target_selector=payload.get("target_selector"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.UPLOAD:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    selector=selector,
                    file_path=payload.get("file_path"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.DETECT_PAGINATION:
            handle_res(
                await BrowserController.execute(
                    action=_mc.DETECT_PAGINATION,
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.SCROLL_TO_BOTTOM:
            handle_res(
                await BrowserController.execute(
                    action=_mc.SCROLL_TO_BOTTOM,
                    selector=selector,
                    payload=payload,
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.WAIT:
            duration = payload.get("seconds") or (
                payload.get("duration_ms", 1000) / 1000.0
            )
            await asyncio.sleep(float(duration))
        elif event_type == _mc.WAIT_FOR:
            handle_res(
                await BrowserController.execute(
                    action=tool_action,
                    selector=payload.get("selector") or selector,
                    state=payload.get("state", "visible"),
                    url_pattern=payload.get("url_pattern"),
                    timeout_ms=timeout_ms,
                    continue_on_error=continue_on_error,
                )
            )
        elif event_type == _mc.SCROLL:
            await BrowserController.execute(
                action=tool_action,
                selector=selector,
                direction=payload.get("direction", "down"),
                amount=payload.get("amount", 300),
                continue_on_error=continue_on_error,
            )
        elif event_type == _mc.SCREENSHOT:
            await BrowserController.execute(
                action=tool_action,
                selector=selector,
                full_page=payload.get("full_page", False),
                continue_on_error=continue_on_error,
            )
        elif event_type == _mc.NEW_TAB:
            await BrowserController.execute(
                action=tool_action,
                url=payload.get("url"),
                continue_on_error=continue_on_error,
            )
        elif event_type == _mc.SWITCH_TAB:
            await BrowserController.execute(
                action=tool_action,
                tab_index=payload.get("tab_index"),
                continue_on_error=continue_on_error,
            )
        elif event_type == _mc.DIALOG_HANDLE:
            await BrowserController.execute(
                action=tool_action,
                dialog_action=payload.get("dialog_action"),
                dialog_text=payload.get("dialog_text"),
                continue_on_error=continue_on_error,
            )
        elif event_type in (_mc.RUN_JS, _mc.EVALUATE):
            res = await BrowserController.execute(
                action=_mc.RUN_JS,
                script=payload.get("script") or payload.get("expression"),
                frame_selector=payload.get("frame_selector"),
                frame_wait_for_selector=payload.get("frame_wait_for_selector"),
                timeout_ms=timeout_ms,
                continue_on_error=continue_on_error,
            )
            handle_res(res)
            # run_js 返回 false/undefined → 步骤未真正生效。默认仅记录可见
            # warning（兼容"已登录跳过/元素不存在继续"的条件性用法）；宏步骤
            # 声明 require_success: true 时视为失败并停止（通用引擎的状态校验）。
            # 返回值带出 false 信号 → step_log 记录步骤未生效，Agent 可据此
            # 判断宏"跑完但没生效"（如列表搜索无结果）。
            if res and isinstance(res, str) and _is_false_result(res):
                if payload.get("require_success", False) and not continue_on_error:
                    raise ValueError(
                        "[macro-engine] run_js required success but returned false: "
                        + str(payload.get("script") or "")[:120]
                    )
                logger.warning(
                    "[macro-engine] run_js step returned false (continue): %s",
                    str(payload.get("script") or "")[:120],
                )
                return False

            # VERIFY 断言：run_js 返回 VERIFY:<state> 且步骤声明 expect:<states> 时，
            # 提取到的业务状态必须匹配预期，否则宏失败。解决"假完成"——宏报
            # completed 但业务状态未按预期变化（如售后仍"申请售后"）。
            # expect 用 "|" 分隔多个可接受状态（如 expect: "待转账|买家待退货"）。
            if res and isinstance(res, str) and "VERIFY:" in res:
                expect = payload.get("expect")
                if expect:
                    actual = res.split("VERIFY:", 1)[1].strip()
                    expected_states = (
                        [e.strip() for e in str(expect).split("|") if e.strip()]
                        if isinstance(expect, str)
                        else [str(e) for e in (expect or [])]
                    )
                    if expected_states and not any(
                        actual == e or actual in e for e in expected_states
                    ):
                        raise ValueError(
                            f"[macro-engine] VERIFY assertion failed: expected {expected_states}, got '{actual}'"
                        )

        # ── 操作后校验（post_verify）─────────────────────────────
        # 允许宏声明"动作后页面应变成什么样"（URL 跳转 / 元素出现），不满足则
        # wait_for 超时返回 ❌ → handle_res 抛异常停止。解决"提交了但没生效"
        # "点了但弹窗没关"等动作成功但效果失败的问题。
        post = payload.get("post_verify")
        if isinstance(post, dict):
            p_url = post.get("url_pattern")
            p_sel = post.get("selector")
            if p_url or p_sel:
                vr = await BrowserController.execute(
                    action=_mc.WAIT_FOR,
                    selector=p_sel,
                    url_pattern=p_url,
                    state=post.get("state", "visible"),
                    timeout_ms=post.get("timeout_ms", 8000),
                )
                handle_res(vr)

        return True

    @classmethod
    async def _execute_desktop_step(
        cls, event_type, selector, payload, skip_recording=False
    ):
        from app.core.environment.controllers import DesktopController

        event_type = event_type.lower() if event_type else event_type
        selector = selector or payload.get("element_name") or payload.get("target")
        tool_action = ActionRegistry.get_tool_action(event_type, _mc.DESKTOP)

        def handle_res(res):
            if res and ("Error:" in str(res) or "❌" in str(res)):
                raise ValueError(res)

        if event_type in (_mc.CLICK, _mc.TAP, _mc.DOUBLE_CLICK):
            optional = payload.get("optional", False)
            res = await DesktopController.execute(
                action=tool_action,
                element_name=selector,
                x=payload.get("x"),
                y=payload.get("y"),
                skip_recording=skip_recording,
            )
            if (
                optional
                and res
                and ("❌" in str(res) or "Could not resolve" in str(res))
            ):
                logger.warning(
                    f"[macro-engine] Optional click '{selector}' failed, continuing"
                )
            else:
                handle_res(res)
        elif event_type in (_mc.INPUT, _mc.TYPE_TEXT):
            handle_res(
                await DesktopController.execute(
                    action=_mc.TYPE_TEXT,
                    text=payload.get("text") or payload.get("value", ""),
                    force_keystroke=payload.get("force_keystroke", False),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.KEY_PRESS:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    key=payload.get("key"),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.SCROLL:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    direction=payload.get("direction", "down"),
                    amount=payload.get("amount", 300),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.DRAG_DROP:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    x=payload.get("x"),
                    y=payload.get("y"),
                    x2=payload.get("x2"),
                    y2=payload.get("y2"),
                    source_element=payload.get("source_element") or selector,
                    target_element=payload.get("target_element"),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.OPEN_APP:
            bundle_id = payload.get("bundle_id")
            if bundle_id and payload.get("focus") is False:
                # Focus-free launch (Atlas-Native): open -b + window poll.
                from app.core.atlas.ax_actions import ensure_pid

                pid = await asyncio.to_thread(ensure_pid, bundle_id)
                if pid is None:
                    raise ValueError(f"Error: open_app failed for {bundle_id}")
            else:
                handle_res(
                    await DesktopController.execute(
                        action=tool_action,
                        app_name=payload.get("app_name") or payload.get("text"),
                        skip_recording=skip_recording,
                    )
                )
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
                ok = await asyncio.to_thread(
                    perform_by_label, pid, payload["role"], payload["label"], ax_action
                )
                if ok:
                    return
            if ax_action:
                ok = await asyncio.to_thread(
                    press_at_path, pid, payload["ax_path"], ax_action
                )
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
                ok = await asyncio.to_thread(
                    set_value_by_label, pid, payload["role"], payload["label"], text
                )
            else:
                ok = False
            if not ok and payload.get("ax_path"):
                ok = await asyncio.to_thread(
                    set_value_at_path, pid, payload["ax_path"], text
                )
            if not ok:
                raise ValueError(
                    f"Error: ax_set_value rejected for {payload.get('label') or payload.get('ax_path')}"
                )
        elif event_type == _mc.WAIT:
            duration = payload.get("seconds") or (
                payload.get("duration", 1000) / 1000.0
            )
            await asyncio.sleep(float(duration))
        elif event_type == _mc.CGCLICK:
            from app.infrastructure.drivers.macos import macos_driver

            win_ox = payload.get("win_offset_x")
            win_oy = payload.get("win_offset_y")
            if win_ox is not None and win_oy is not None:
                from app.core.environment import get_current_app_context

                app_info = await asyncio.to_thread(get_current_app_context)
                bounds_str = app_info.bounds
                if bounds_str:
                    wx, wy, _, _ = map(int, bounds_str.split(","))
                    x = wx + int(win_ox)
                    y = wy + int(win_oy)
                else:
                    x, y = int(win_ox), int(win_oy)
            else:
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
            await asyncio.to_thread(macos_driver.click, x, y)
        elif event_type == _mc.APPLESCRIPT:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    script=payload.get("script"),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.SCREENSHOT:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    region=payload.get("region"),
                    interactive=payload.get("interactive"),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.GET_ACTIVE_APP:
            handle_res(
                await DesktopController.execute(
                    action=tool_action, skip_recording=skip_recording
                )
            )
        elif event_type == _mc.GET_INFO:
            handle_res(
                await DesktopController.execute(
                    action=tool_action,
                    app_name=payload.get("app_name"),
                    skip_recording=skip_recording,
                )
            )
        elif event_type == _mc.DUMP_UI:
            handle_res(
                await DesktopController.execute(
                    action=tool_action, skip_recording=skip_recording
                )
            )

    @classmethod
    async def _execute_mobile_step(
        cls, event_type, selector, payload, disable_ocr=True, expected_pkg=None
    ):
        from app.core.environment.controllers import MobileController

        event_type = event_type.lower() if event_type else event_type
        tool_action = ActionRegistry.get_tool_action(event_type, _mc.MOBILE)

        def handle_res(res):
            if res and isinstance(res, str):
                if (
                    "Error:" in res
                    or "Execution failed:" in res
                    or res.startswith("ERR_")
                    or "❌" in res
                ):
                    raise ValueError(res)

        def _get_coords(p, key):
            val = p.get(key)
            if val is not None:
                return val

            alias_map = {
                "x": "start_x",
                "y": "start_y",
                "x2": "end_x",
                "y2": "end_y",
                "end_x": "x2",
                "end_y": "y2",
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

        if event_type in (_mc.CLICK, _mc.TAP):
            logger.info("[_execute_mobile_step] Branch: click/tap")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            if x is not None and y is not None:
                handle_res(
                    await MobileController.execute(
                        action=tool_action,
                        x=x,
                        y=y,
                        element_name=None,
                        timeout=payload.get("timeout", 8.0),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        disable_ocr=disable_ocr,
                        fast_probe=True,
                        passive_safety=True,
                    )
                )
            else:
                handle_res(
                    await MobileController.execute(
                        action=tool_action,
                        x=x,
                        y=y,
                        element_name=selector
                        or payload.get("element_name")
                        or payload.get("target"),
                        timeout=payload.get("timeout", 8.0),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        disable_ocr=disable_ocr,
                        fast_probe=True,
                        passive_safety=True,
                    )
                )
        elif event_type == _mc.LONG_PRESS:
            logger.info("[_execute_mobile_step] Branch: long_press")
            x, y = _get_coords(payload, "x"), _get_coords(payload, "y")
            if x is not None and y is not None:
                handle_res(
                    await MobileController.execute(
                        action=tool_action,
                        x=x,
                        y=y,
                        element_name=None,
                        duration_ms=payload.get("duration_ms", 800),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        disable_ocr=disable_ocr,
                        fast_probe=True,
                        passive_safety=True,
                    )
                )
            else:
                handle_res(
                    await MobileController.execute(
                        action=tool_action,
                        x=x,
                        y=y,
                        element_name=selector or payload.get("element_name"),
                        duration_ms=payload.get("duration_ms", 800),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        disable_ocr=disable_ocr,
                        fast_probe=True,
                        passive_safety=True,
                    )
                )
        elif event_type in (_mc.INPUT, _mc.TYPE_TEXT):
            handle_res(
                await MobileController.execute(
                    action=_mc.INPUT_TEXT,
                    text=payload.get("text") or payload.get("value", ""),
                    element_name=selector or payload.get("element_name"),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type in (_mc.SWIPE, _mc.SCROLL):
            actual_action = tool_action
            if (
                event_type == _mc.SWIPE
                and payload.get("direction")
                and _get_coords(payload, "x") is None
            ):
                actual_action = _mc.SCROLL

            handle_res(
                await MobileController.execute(
                    action=actual_action,
                    x=_get_coords(payload, "x"),
                    y=_get_coords(payload, "y"),
                    x2=_get_coords(payload, "x2"),
                    y2=_get_coords(payload, "y2"),
                    direction=payload.get("direction"),
                    scroll_amount=payload.get("distance")
                    or payload.get("scroll_amount", "medium"),
                    duration_ms=payload.get("duration_ms", 500),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.BACK:
            handle_res(
                await MobileController.execute(
                    action="press_key",
                    keycode="back",
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.BACK_KEY:
            handle_res(
                await MobileController.execute(
                    action="press_key",
                    keycode=payload.get("keycode", "back"),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.HOME:
            handle_res(
                await MobileController.execute(
                    action="press_key",
                    keycode="home",
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.KEY_PRESS:
            handle_res(
                await MobileController.execute(
                    action=tool_action,
                    keycode=payload.get("key") or payload.get("keycode"),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.OPEN_APP:
            handle_res(
                await MobileController.execute(
                    action=tool_action,
                    text=payload.get("package_name")
                    or payload.get("package")
                    or payload.get("text")
                    or payload.get("app_name"),
                    force_stop=payload.get("force_stop", True),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.SCREENSHOT:
            handle_res(
                await MobileController.execute(
                    action=tool_action,
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.DUMP_UI:
            handle_res(
                await MobileController.execute(
                    action=tool_action,
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                    compressed_dump=False,
                )
            )
        elif event_type == _mc.WAIT:
            duration = payload.get("seconds") or (
                payload.get("duration_ms", 1000) / 1000.0
            )
            await asyncio.sleep(float(duration))
        elif event_type == "get_clipboard":
            handle_res(
                await MobileController.execute(
                    action="get_clipboard",
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                )
            )
        elif event_type == _mc.SCROLL_TO_BOTTOM:
            handle_res(
                await MobileController.execute(
                    action=_mc.SCROLL_TO_BOTTOM,
                    max_scrolls=payload.get("max_scrolls", 5),
                    scroll_amount=payload.get("scroll_amount", "medium"),
                    delay_ms=payload.get("delay_ms", 1000),
                    disable_atlas=True,
                    disable_trace_screenshot=True,
                    disable_ocr=disable_ocr,
                    fast_probe=True,
                    passive_safety=True,
                    compressed_dump=False,
                )
            )
