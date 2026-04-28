import logging
from typing import Any

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.healing_policy import SelfHealingPolicy
from app.core.execution.macro.optimizer import MacroOptimizer
from app.core.execution.macro.schemas import MacroRunResult, MacroScript
from app.core.monitoring.activity import activity_monitor

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
        skill: Any | None = None  # LearnedSkill, optional for policy check
    ) -> MacroRunResult:
        """
        High-level entry point to execute a macro.
        Handles: Validation, Activity Monitoring, Parameters, and Engine Dispatch.
        
        Args:
            thread_id: The conversation thread ID
            script_input: Macro script (MacroScript object or list of step dicts)
            params: Execution parameters (optional)
            skill: The LearnedSkill being executed (optional, for self-healing policy)
        """
        # 1. Validation / Hydration
        try:
            if isinstance(script_input, list):
                script = MacroScript(steps=script_input)
            else:
                script = script_input
        except Exception as e:
            logger.error(f"[{thread_id}] Macro validation failed: {e}")
            return MacroRunResult(success=False, message=f"Invalid macro format: {e}")

        if not script.steps:
            logger.warning(f"[{thread_id}] Macro execution skipped: script is empty.")
            return MacroRunResult(success=False, message="Macro script is empty")

        logger.info(f"[{thread_id}] Starting Standardized Macro Execution ({len(script.steps)} steps)")
        if params is None:
            params = {}

        # 2. Activity Monitoring
        await activity_monitor.start_run(thread_id)

        extracted_data = {}
        try:
            # 3. Engine Dispatch
            success, msg, fallback_ctx = await MacroEngine.execute_steps(
                thread_id, script.steps, params, extracted_data
            )

            if not success:
                logger.error(f"[{thread_id}] Macro execution failed: {msg}")
                await activity_monitor.end_run(thread_id, "failed")

                # --- Unified Self-Healing Decision ---
                decision = SelfHealingPolicy.check(skill=skill, execution_params=params)

                if not decision.allowed:
                    logger.warning(f"[{thread_id}] Self-healing disabled: {decision.reason}")
                    return MacroRunResult(
                        success=False,
                        message=msg,
                        allow_self_healing=False,
                        healing_disabled_reason=decision.reason,
                        healing_disabled_source=decision.source,
                    )

                # Self-healing is allowed - trigger fallback via event system
                from app.core.events import system_bus
                from app.core.execution.macro.event import MacroExecutionFailedEvent

                event = MacroExecutionFailedEvent(
                    skill_id=params.get("_skill_id") if params else None,
                    skill_name=params.get("_skill_name") if params else "manual_macro",
                    error_message=msg,
                    fallback_context=fallback_ctx,
                    thread_id=thread_id
                )

                # Publish event for listeners (advisor will add suggestions)
                from app.core.execution.macro.event.publishers import publish_macro_execution_failed
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
            await activity_monitor.log_event("macro_thought", {"text": "Macro execution completed successfully."}, thread_id)
            await activity_monitor.end_run(thread_id, "done")
            return MacroRunResult(
                success=True,
                message="Deterministic Macro Execution Complete.",
                extracted_data=extracted_data
            )

        except Exception as e:
            logger.error(f"[{thread_id}] Macro service crash: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, "failed")
            return MacroRunResult(success=False, message=f"System error during macro execution: {str(e)}")

    @classmethod
    def optimize(cls, script_input: MacroScript | list[dict]) -> MacroScript:
        """
        Utility to optimize a macro script.
        """
        if isinstance(script_input, list):
            script = MacroScript(steps=script_input)
        else:
            script = script_input

        optimizer = MacroOptimizer()
        optimized_script, stats = optimizer.optimize(script)

        if stats.reduction_ratio > 0:
            logger.info(f"Macro optimized via Service: {stats}")

        return optimized_script

    @classmethod
    def validate(cls, raw_data: Any) -> MacroScript:
        """
        Strict validation of macro data.
        """
        if isinstance(raw_data, list):
            return MacroScript(steps=raw_data)
        elif isinstance(raw_data, dict):
            return MacroScript.parse_obj(raw_data)
        elif isinstance(raw_data, MacroScript):
            return raw_data
        raise ValueError("Unsupported macro data type for validation")
