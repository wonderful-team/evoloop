import logging
from typing import Any, Dict, List, Optional, Union

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.optimizer import MacroOptimizer
from app.core.execution.macro.schema import MacroScript
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
        script_input: Union[MacroScript, List[Dict]], 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        High-level entry point to execute a macro.
        Handles: Validation, Activity Monitoring, Parameters, and Engine Dispatch.
        """
        # 1. Validation / Hydration
        try:
            if isinstance(script_input, list):
                script = MacroScript(steps=script_input)
            else:
                script = script_input
        except Exception as e:
            logger.error(f"[{thread_id}] Macro validation failed: {e}")
            return {"success": False, "message": f"Invalid macro format: {e}"}

        if not script.steps:
            logger.warning(f"[{thread_id}] Macro execution skipped: script is empty.")
            return {"success": False, "message": "Macro script is empty"}

        logger.info(f"[{thread_id}] Starting Standardized Macro Execution ({len(script.steps)} steps)")
        
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
                result = {"success": False, "message": msg}
                if fallback_ctx:
                    result["status"] = "fallback_required"
                    result["fallback_context"] = fallback_ctx
                return result

            # 4. Success Reporting
            await activity_monitor.log_event("macro_thought", {"text": "Macro execution completed successfully."}, thread_id)
            await activity_monitor.end_run(thread_id, "done")
            return {
                "success": True, 
                "message": "Deterministic Macro Execution Complete.", 
                "extracted_data": extracted_data
            }

        except Exception as e:
            logger.error(f"[{thread_id}] Macro service crash: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, "failed")
            return {"success": False, "message": f"System error during macro execution: {str(e)}"}

    @classmethod
    def optimize(cls, script_input: Union[MacroScript, List[Dict]]) -> MacroScript:
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
