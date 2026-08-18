import logging
from typing import Any

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.event.publishers import publish_macro_execution_failed
from app.core.execution.macro.healing_policy import SelfHealingPolicy
from app.core.execution.macro.schemas import MacroRunResult, MacroScript
from app.core.monitoring.activity import activity_monitor
from app.models.macro import Macro

logger = logging.getLogger(__name__)


class MacroService:
    """
    The unified Orchestrator for Macro Logic.
    Provides a clean API for SkillSynthesizer, Agents, and Workflows.
    """

    @classmethod
    async def run(
        cls,
        thread_id: str,
        script_input: MacroScript | list[dict],
        params: dict[str, Any] | None = None,
        macro: Macro | None = None,  # Macro, optional for policy check
    ) -> MacroRunResult:
        """
        High-level entry point to execute a macro.
        Handles: Validation, Activity Monitoring, Parameters, and Engine Dispatch.

        Args:
            thread_id: The conversation thread ID
            script_input: Macro script (MacroScript object or list of step dicts)
            params: Execution parameters (optional)
            macro: The Macro being executed (optional, for self-healing policy)
        """
        # 1. Validation / Hydration
        try:
            if isinstance(script_input, list):
                script = MacroScript(steps=script_input)
            else:
                script = script_input
        except Exception:
            logger.exception("[%s] Macro validation failed", thread_id)
            return MacroRunResult(success=False, message="Invalid macro format")

        if not script.steps:
            logger.warning(f"[{thread_id}] Macro execution skipped: script is empty.")
            return MacroRunResult(success=False, message="Macro script is empty")

        logger.info(f"[{thread_id}] Starting Standardized Macro Execution ({len(script.steps)} steps)")
        if params is None:
            params = {}

        # 集中解析 {{base_url}}（MacroService 直连路径：自愈重试/工具调用）。
        # MacroEngine.run 已做同样注入，但自愈重试（runner._run_with_self_heal）
        # 与直接调用方绕过 run()，直接进 execute_steps，故此处必须兜底。
        # 仅在成功解析时注入；macro 为 None（如纯脚本验证）时无法定位项目，跳过。
        if macro is not None and "base_url" not in params:
            from app.core.execution.macro.runner import resolve_project_base_url

            base_url = await resolve_project_base_url(macro.project_id)
            if base_url:
                params["base_url"] = base_url

        # 2. Activity Monitoring
        await activity_monitor.start_run(thread_id)

        extracted_data = {}
        try:
            # 3. Engine Dispatch
            success, msg, fallback_ctx = await MacroEngine.execute_steps(
                thread_id, script.steps, params, extracted_data
            )

            if not success:
                logger.error("[%s] Macro execution failed: %s", thread_id, msg)
                await activity_monitor.end_run(thread_id, "failed")

                # --- Unified Self-Healing Decision ---
                decision = SelfHealingPolicy.check(macro=macro, execution_params=params)

                if not decision.allowed:
                    logger.warning("[%s] Self-healing disabled: %s", thread_id, decision.reason)
                    return MacroRunResult(
                        success=False,
                        message=msg,
                        allow_self_healing=False,
                        healing_disabled_reason=decision.reason,
                        healing_disabled_source=decision.source,
                    )

                # Self-healing is allowed - trigger fallback via event system
                event = await publish_macro_execution_failed(
                    skill_id=params.get("_skill_id") if params else None,
                    skill_name=params.get("_skill_name") if params else "manual_macro",
                    error_message=msg,
                    fallback_context=fallback_ctx,
                    thread_id=thread_id,
                )

                return MacroRunResult(
                    success=False,
                    message=msg,
                    allow_self_healing=True,
                    suggestions=event.suggestions,
                    status="fallback_required",
                    fallback_context=fallback_ctx,
                )

            # 4. Success Reporting
            await activity_monitor.log_event(
                "macro_thought",
                {"text": "Macro execution completed successfully."},
                thread_id,
            )
            await activity_monitor.end_run(thread_id, "done")
            return MacroRunResult(
                success=True,
                message="Deterministic Macro Execution Complete.",
                extracted_data=extracted_data,
            )

        except Exception as e:
            logger.error(f"[{thread_id}] Macro service crash: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, "failed")
            return MacroRunResult(success=False, message=f"System error during macro execution: {str(e)}")
