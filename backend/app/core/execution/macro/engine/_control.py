import logging

from app.core.execution.macro.schemas import MacroSource, MacroStepType

logger = logging.getLogger(__name__)


class ControlMixin:
    @classmethod
    async def _handle_control_flow(
        cls,
        thread_id,
        step,
        payload,
        params,
        extracted_data,
        disable_ocr=True,
        active_bundle_id=None,
        execution_warnings=None,
    ):
        if params is None:
            params = {}
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
                return await cls.execute_steps(
                    thread_id,
                    branch,
                    params,
                    extracted_data,
                    disable_ocr,
                    active_bundle_id,
                    execution_warnings=execution_warnings,
                )

        elif step.type == MacroStepType.LOOP:
            collect_mode = step.collect_mode
            if collect_mode in ("list", "detail", "auto"):
                return await cls._handle_collect_loop(
                    thread_id,
                    step,
                    payload,
                    params,
                    extracted_data,
                    disable_ocr,
                    collect_mode,
                    active_bundle_id,
                    execution_warnings=execution_warnings,
                )

            if payload.get("items_key"):
                return await cls._handle_loop(
                    thread_id,
                    step,
                    payload,
                    params,
                    extracted_data,
                    disable_ocr,
                    active_bundle_id,
                    execution_warnings=execution_warnings,
                )

            iterations = 0
            if not step.steps:
                if execution_warnings is not None:
                    execution_warnings.append(
                        f"loop step {step.step_number} 无循环体（空 steps）"
                    )
                return True, "", None

            max_iters = payload.get("max_iterations", step.max_iterations)
            if isinstance(max_iters, str):
                try:
                    max_iters = int(max_iters)
                except ValueError:
                    max_iters = 5

            while iterations < max_iters:
                if cond_type is not None:
                    is_true = await cls._evaluate_condition(cond_type, selector, step.source)
                    if not is_true:
                        break

                loop_params = dict(params) if params else {}
                loop_params["loop_index"] = iterations

                success, msg, fallback = await cls.execute_steps(
                    thread_id,
                    step.steps,
                    loop_params,
                    extracted_data,
                    disable_ocr,
                    active_bundle_id,
                )

                if not success:
                    if not fallback:
                        fallback = {"failed_step": step.model_copy().model_dump()}
                    fallback["loop_progress"] = {
                        "loop_step_number": step.step_number,
                        "current_iteration": iterations,
                        "max_iterations": max_iters,
                        "condition": cond_type,
                    }
                    return False, msg, fallback

                iterations += 1

            if iterations == 0:
                if execution_warnings is not None:
                    execution_warnings.append(
                        f"loop step {step.step_number} 迭代 0 次"
                        + (f"（条件 {cond_type}: {selector} 未命中）" if cond_type else "")
                    )
            elif iterations >= max_iters:
                logger.warning(f"[{thread_id}] While loop reached max iterations ({max_iters})")

        return True, "", None

    @classmethod
    async def _evaluate_condition(cls, cond_type, selector, source):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.environment.controllers.mobile import MobileController

        if cond_type == "element_exists":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="check_element", selector=selector)
                return "Found" in str(res)
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(
                    action="applescript",
                    script=f'tell application "System Events" to exists (first UI element whose name contains "{selector}")',
                )
                return "true" in str(res).lower()

        elif cond_type == "element_visible":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="check_element", selector=selector)
                return "visible=True" in str(res)
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(
                    action="applescript",
                    script=f'tell application "System Events" to get visible of (first UI element whose name contains "{selector}")',
                )
                return "true" in str(res).lower()

        elif cond_type == "text_contains":
            if source == MacroSource.DOM:
                res = await BrowserController.execute(action="get_text")
                return selector in str(res) if res else False
            elif source in (MacroSource.MOBILE, MacroSource.GLOBAL):
                res = await MobileController.execute(action="dump_ui")
                return selector in str(res)
            elif source == MacroSource.DESKTOP:
                res = await DesktopController.execute(
                    action="applescript",
                    script=f'tell application "System Events" to get name of every UI element whose name contains "{selector}"',
                )
                return len(str(res)) > 5

        elif cond_type in ("has_more_items", "more_items", "pagination_exists"):
            return True

        return False
