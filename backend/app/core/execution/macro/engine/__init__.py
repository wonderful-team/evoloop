import logging
import re
from typing import Any

from app.core.context import ContextManager, EvoContext
from app.core.execution.macro.engine._bash import BashMixin
from app.core.execution.macro.engine._control import ControlMixin
from app.core.execution.macro.engine._dump import DumpMixin
from app.core.execution.macro.engine._executors import ExecutorMixin
from app.core.execution.macro.engine._extraction import ExtractionMixin
from app.core.execution.macro.engine._loops import LoopMixin
from app.core.execution.macro.engine._native import NativeMixin
from app.core.execution.macro.schemas import MacroSource, MacroStepType
from app.core.monitoring.activity import activity_monitor
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Error as _PlaywrightError
except ImportError:  # playwright is an optional dependency outside DOM macros
    _PlaywrightError = TimeoutError

# Playwright errors (TimeoutError on a stale selector, TargetClosedError, ...)
# are NOT subclasses of the stdlib types below; without listing them a single
# timed-out selector escaped the engine and crashed the voice dispatcher.
_STEP_EXCEPTIONS = (
    ValueError,
    OSError,
    RuntimeError,
    TypeError,
    KeyError,
    _PlaywrightError,
)


class MacroEngine(
    ControlMixin,
    LoopMixin,
    ExtractionMixin,
    DumpMixin,
    NativeMixin,
    BashMixin,
    ExecutorMixin,
):
    @classmethod
    async def execute(
        cls,
        thread_id: str,
        script: Any,
        params: dict[str, Any] | None = None,
        extracted_data: dict[str, Any] | None = None,
        disable_ocr: bool = True,
        skip_activity_log: bool = False,
        skip_recording: bool = False,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        return await cls.execute_steps(
            thread_id=thread_id,
            steps=script.steps,
            params=params,
            extracted_data=extracted_data,
            disable_ocr=disable_ocr,
            active_bundle_id=params.get("package_name") or params.get("bundle_id") if params else None,
            skip_activity_log=skip_activity_log,
            skip_recording=skip_recording,
        )

    @classmethod
    async def execute_steps(
        cls,
        thread_id: str,
        steps: list,
        params: dict[str, Any] | None = None,
        extracted_data: dict[str, Any] | None = None,
        disable_ocr: bool = True,
        active_bundle_id: str | None = None,
        skip_activity_log: bool = False,
        skip_recording: bool = False,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if extracted_data is None:
            extracted_data = {}
        if params is None:
            params = {}

        # Bind the execution context so downstream tools (browser, etc.) can
        # resolve the current thread_id and provide per-thread isolation.
        ctx = ContextManager.current()
        token = None
        if ctx.thread_id != thread_id or ctx.request_id == "global-fallback":
            ctx = EvoContext(
                thread_id=thread_id,
                request_id=gen_uuid(),
                project_id=ctx.project_id,
                member_id=ctx.member_id,
            )
            token = ContextManager.set(ctx)
        try:
            return await cls._execute_steps_inner(
                thread_id,
                steps,
                params,
                extracted_data,
                disable_ocr,
                active_bundle_id,
                skip_activity_log=skip_activity_log,
                skip_recording=skip_recording,
            )
        finally:
            if token:
                ContextManager.reset(token)

    @classmethod
    async def _execute_steps_inner(
        cls,
        thread_id: str,
        steps: list,
        params: dict[str, Any],
        extracted_data: dict[str, Any],
        disable_ocr: bool,
        active_bundle_id: str | None,
        skip_activity_log: bool = False,
        skip_recording: bool = False,
    ) -> tuple[bool, str, dict[str, Any] | None]:

        for step in steps:
            step_num = step.step_number

            target_selector = cls._inject_params(step.target_selector, params)
            payload = cls._inject_payload_params(step.payload, params)

            target_selector = target_selector or payload.get("selector")

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
            elif step.type == MacroStepType.BASH:
                desc += f"(command='{str(payload.get('command', ''))[:60]}')"

            if not skip_activity_log:
                await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
            logger.info(f"[{thread_id}] {desc}")

            if step.type in (
                MacroStepType.CONTROL,
                MacroStepType.IF,
                MacroStepType.LOOP,
            ):
                success, msg, fallback = await cls._handle_control_flow(
                    thread_id,
                    step,
                    payload,
                    params,
                    extracted_data,
                    disable_ocr,
                    active_bundle_id,
                )
                if not success:
                    return False, msg, fallback
                continue

            if step.type == MacroStepType.EXTRACT:
                try:
                    await cls._handle_extraction(
                        thread_id,
                        step,
                        target_selector,
                        payload,
                        params,
                        extracted_data,
                    )
                except _STEP_EXCEPTIONS as e:
                    error_msg = str(e)
                    screenshot_path = await cls._debug_screenshot(step.source)
                    await cls._handle_action_error(
                        thread_id,
                        step_num,
                        step.event_type or "extract",
                        error_msg,
                        screenshot_path,
                    )
                    return (
                        False,
                        error_msg,
                        {
                            "screenshot_path": screenshot_path,
                            "step_number": step_num,
                            "event_type": step.event_type or "extract",
                        },
                    )
                # Two-stage macros: extracted values become {{key}} references
                # for downstream steps. Explicit caller params win; failed
                # extractions (None) stay unresolved and trip the URL guard.
                params = {
                    **{k: v for k, v in extracted_data.items() if v is not None},
                    **params,
                }
                continue

            if step.type == MacroStepType.DUMP:
                await cls._handle_dump(thread_id, payload, extracted_data)
                continue

            if step.type == MacroStepType.NATIVE:
                await cls._handle_native(thread_id, payload, extracted_data)
                continue

            if step.type == MacroStepType.BASH:
                try:
                    await cls._execute_bash_step(thread_id, payload, extracted_data)
                except _STEP_EXCEPTIONS as e:
                    error_msg = str(e)
                    await cls._handle_action_error(
                        thread_id, step_num, "bash", error_msg
                    )
                    return (
                        False,
                        error_msg,
                        {
                            "step_number": step_num,
                            "event_type": "bash",
                        },
                    )
                continue

            if step.type == MacroStepType.ACTION:
                event_type = step.event_type
                source = step.source

                if event_type == "navigate":
                    nav_url = payload.get("url")
                    if isinstance(nav_url, str) and "{{" in nav_url:
                        if "base_url" in nav_url:
                            unresolved = (
                                f"宏需要后台站点地址（url）才能执行。"
                                f"请在项目详情页 → Profile 中设置「部署 URL」。"
                                f"未解析 URL: {nav_url}"
                            )
                        else:
                            unresolved = f"导航 URL 含未解析参数: {nav_url}"
                        await cls._handle_action_error(thread_id, step_num, event_type, unresolved)
                        return (
                            False,
                            unresolved,
                            {"step_number": step_num, "event_type": event_type},
                        )

                if event_type == "open_app":
                    new_pkg = (
                        payload.get("package_name")
                        or payload.get("package")
                        or payload.get("text")
                        or payload.get("app_name")
                    )
                    if new_pkg:
                        active_bundle_id = new_pkg
                        logger.info(f"[{thread_id}] Active package updated to: {active_bundle_id}")

                try:
                    if source == MacroSource.DOM:
                        await cls._execute_browser_step(event_type, target_selector, payload)
                    elif source == MacroSource.MOBILE:
                        await cls._execute_mobile_step(
                            event_type,
                            target_selector,
                            payload,
                            disable_ocr,
                            expected_pkg=active_bundle_id,
                        )
                    elif source == MacroSource.DESKTOP:
                        await cls._execute_desktop_step(
                            event_type,
                            target_selector,
                            payload,
                            skip_recording=skip_recording,
                        )
                    else:
                        logger.warning(f"Unknown macro source: {source}")
                except _STEP_EXCEPTIONS as e:
                    error_msg = str(e)
                    screenshot_path = await cls._debug_screenshot(source)
                    await cls._handle_action_error(thread_id, step_num, event_type, error_msg, screenshot_path)
                    return (
                        False,
                        error_msg,
                        {
                            "screenshot_path": screenshot_path,
                            "step_number": step_num,
                            "event_type": event_type,
                        },
                    )

        return True, "", None

    @classmethod
    async def _debug_screenshot(cls, source) -> str | None:
        if source != MacroSource.DOM:
            return None
        try:
            from app.core.environment.controllers.browser import BrowserController

            res = await BrowserController.execute(action="screenshot", purpose="debug")
            match = re.search(r"(/.*\.png)", str(res))
            return match.group(1) if match else None
        except _STEP_EXCEPTIONS:
            return None

    @classmethod
    async def _handle_action_error(cls, thread_id, step_num, event_type, error_msg, screenshot_path=None):
        logger.error(f"[{thread_id}] Step {step_num} ({event_type}) failed: {error_msg}")
        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Step {step_num} failed: {error_msg[:200]}"},
            thread_id,
        )
        if screenshot_path:
            logger.info(f"[{thread_id}] Screenshot saved: {screenshot_path}")

    @classmethod
    def _inject_params(cls, value: str | None, params: dict | None) -> str | None:
        if not value:
            return value
        if not params:
            params = {}

        def _get_nested(data: dict, path: str):
            parts = path.split(".")
            curr = data
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                else:
                    return None
            return curr

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
        # Pydantic payloads (MacroPayload union, e.g. NavigationPayload) are not
        # dicts: without this branch `{{ param }}` inside any structured payload
        # was silently never injected.
        from pydantic import BaseModel

        if isinstance(payload, BaseModel):
            payload = payload.model_dump()
        if isinstance(payload, dict):
            return {k: cls._inject_payload_params(v, params) for k, v in payload.items()}
        elif isinstance(payload, list):
            return [cls._inject_payload_params(item, params) for item in payload]
        return payload
