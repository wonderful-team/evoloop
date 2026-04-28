"""
AgentMacroValidator - Agent-based Macro Verification System

The main orchestrator for active macro verification.
Manages multi-round verification, anomaly detection, and macro evolution.
"""

import asyncio
import copy
import logging
import time
from typing import Any

from app.core.execution.macro.evolution_engine import MacroEvolutionEngine
from app.core.execution.macro.models import (
    AdaptationRecord,
    AnomalyType,
    ExecutionDetail,
    ExecutionMode,
    MacroEvolutionRecord,
    RedundancyCheckResult,
    ReportSummary,
    RoundConfig,
    RoundReport,
    StepExecutionStatus,
    StepResult,
    VerificationAgentConfig,
    VerificationIssue,
    VerificationReport,
    VerificationRequest,
    VerificationResponse,
    VerificationStatus,
)
from app.core.execution.macro.optimizer import MacroOptimizer
from app.core.execution.macro.reasoning_engine import AgentReasoningEngine
from app.core.execution.macro.round_orchestrator import (
    BaselineStrategy,
    ChaosStrategy,
    RoundOrchestrator,
    StressTestStrategy,
)
from app.core.execution.macro.verification_worker import VerificationWorker

logger = logging.getLogger(__name__)


class AgentMacroValidator:
    """
    Agent-based Macro Validator

    Orchestrates the verification process:
    1. Multi-round execution (baseline + interference)
    2. Real-time anomaly detection
    3. Strategy adaptation
    4. Macro evolution
    5. Report generation
    """

    def __init__(self, request: VerificationRequest):
        self.request = request
        self.agent_config = request.agent_config or VerificationAgentConfig()
        # Phase 4: Perception-First Reasoning Engine
        self.reasoning_engine = AgentReasoningEngine(
            mental_model=request.instructions or "Execute the macro faithfully and handle UI anomalies proactively."
        )

        self.worker: VerificationWorker | None = None

        # Phase 4: Round orchestration
        self.orchestrator = self._create_orchestrator()

        # Execution state
        self.execution_history: list[dict[str, Any]] = []
        self.adaptation_records: list[AdaptationRecord] = []
        self.round_reports: list[RoundReport] = []

        # Evolution tracking
        self.evolution_records: list[MacroEvolutionRecord] = []
        self.current_macro: list[dict[str, Any]] = [
            copy.deepcopy(s.model_dump() if hasattr(s, 'model_dump') else s)
            for s in request.macro_script
        ]

        # Statistics
        self.total_anomalies = 0
        self.total_adaptations = 0
        self.start_time: float | None = None

        # Redundancy detection state
        self._executed_steps: list[StepResult] = []
        self._redundant_step_numbers: set = set()

    def _create_orchestrator(self) -> RoundOrchestrator:
        """Create round orchestrator based on request configuration"""
        # Determine strategy based on max_rounds
        strategies = []

        if self.request.max_rounds >= 1:
            strategies.append(BaselineStrategy())

        if self.request.max_rounds >= 2:
            # Second round: stress test
            strategies.append(StressTestStrategy(intensity=0.5))

        if self.request.max_rounds >= 3:
            # Third round: chaos
            strategies.append(ChaosStrategy(intensity=0.7))

        return RoundOrchestrator(
            strategies=strategies,
            enable_interference=True
        )

    async def validate(self) -> VerificationResponse:
        """
        Main entry point: Execute full verification workflow

        Phase 4: Uses RoundOrchestrator for multi-round execution with interference injection.
        """
        self.start_time = time.time()
        logger.info(f"[Validator] Starting validation for {len(self.current_macro)} steps")

        try:
            # Initialize worker
            self.worker = await self._create_worker()

            # Phase 4: Execute rounds using orchestrator
            round_num = 1
            while round_num <= self.request.max_rounds:
                # Prepare round with orchestrator (applies interference)
                base_config = self._get_round_config(round_num)
                round_config, round_macro = self.orchestrator.prepare_round(
                    round_number=round_num,
                    base_config=base_config,
                    macro_script=self.current_macro,
                    previous_reports=self.round_reports
                )

                # Check if orchestrator says we should continue
                if round_num > 1 and not self.orchestrator.should_continue(
                    round_num - 1, self.round_reports
                ):
                    logger.info(f"[Validator] Orchestrator decided to stop after round {round_num - 1}")
                    break

                # Execute the round
                logger.info(f"[Validator] Executing round {round_num}: {round_config.round_name}")
                round_report = await self._execute_round(round_num, round_config, round_macro)
                self.round_reports.append(round_report)

                # Log interference summary
                if round_config.inject_anomalies:
                    interference_summary = self.orchestrator.get_interference_summary(round_macro)
                    logger.info(
                        f"[Validator] Round {round_num} interference: "
                        f"{interference_summary['interfered_steps']}/{interference_summary['total_steps']} steps affected"
                    )

                # Stop if critical failure (unless chaos mode)
                if round_report.status == VerificationStatus.FAILED:
                    is_chaos = round_config.environment_overrides.get("chaos_mode", False)
                    if not is_chaos:
                        logger.warning(f"[Validator] Round {round_num} failed, stopping verification")
                        break
                    else:
                        logger.info(f"[Validator] Round {round_num} failed in chaos mode (expected)")

                round_num += 1

            # Generate final response
            return await self._build_response()

        except Exception as e:
            logger.error(f"[Validator] Verification failed: {e}")
            return self._build_error_response(str(e))

        finally:
            if self.worker:
                await self.worker.cleanup()

    async def _create_worker(self) -> VerificationWorker:
        """Create and initialize verification worker"""
        worker = VerificationWorker(
            environment_config=self.request.target_environment,
            agent_config=self.agent_config,
            thread_id=self.request.thread_id
        )
        await worker.initialize()
        return worker

    def _get_round_config(self, round_num: int) -> RoundConfig:
        """Get configuration for specific round"""
        if round_num <= len(self.request.round_configs):
            return self.request.round_configs[round_num - 1]

        # Default config
        return RoundConfig(
            round_name=f"round_{round_num}",
            timeout_per_step=self.agent_config.max_retries_per_step * 30
        )

    async def _execute_round(
        self,
        round_num: int,
        config: RoundConfig,
        macro_script: list[dict[str, Any]] | None = None
    ) -> RoundReport:
        """
        Execute a single verification round
        """
        from datetime import datetime

        # Use provided macro script or default to current macro
        steps_to_execute = macro_script if macro_script is not None else self.current_macro

        logger.info(f"[Validator] Starting round {round_num}: {config.round_name}")

        report = RoundReport(
            round_number=round_num,
            round_name=config.round_name,
            status=VerificationStatus.RUNNING,
            total_steps=len(steps_to_execute),
            started_at=datetime.now()
        )

        step_results: list[StepResult] = []

        for step_idx, step in enumerate(steps_to_execute):
            step_number = step_idx + 1

            # Execute step with adaptation loop
            step_result = await self._execute_step_with_adaptation(
                step=step,
                step_number=step_number,
                round_config=config
            )

            step_results.append(step_result)

            # Update statistics
            if step_result.status == StepExecutionStatus.PASSED:
                report.passed_steps += 1
            elif step_result.status == StepExecutionStatus.ADAPTED:
                report.adapted_steps += 1
            elif step_result.status == StepExecutionStatus.FAILED:
                report.failed_steps += 1
                # Decide whether to continue or abort
                if not await self._should_continue_after_failure(step_result):
                    report.status = VerificationStatus.PARTIAL_FAILED
                    break
            elif step_result.status == StepExecutionStatus.SKIPPED:
                report.skipped_steps += 1

        # Capture environment snapshot
        if self.worker:
            report.environment_snapshot = await self.worker.capture_state()

        report.step_results = step_results
        report.completed_at = datetime.now()

        # Determine round status
        if report.failed_steps == 0:
            report.status = VerificationStatus.COMPLETED
        elif report.passed_steps > 0 or report.adapted_steps > 0:
            report.status = VerificationStatus.PARTIAL_FAILED
        else:
            report.status = VerificationStatus.FAILED

        logger.info(
            f"[Validator] Round {round_num} completed: "
            f"passed={report.passed_steps}, adapted={report.adapted_steps}, "
            f"failed={report.failed_steps}"
        )

        return report

    async def _check_step_redundancy(
        self,
        step: dict[str, Any],
        ui_state: dict[str, Any],
        step_number: int = None
    ) -> RedundancyCheckResult:
        """
        Check if a step is redundant using Agentic perception.
        """
        step_num = step_number or step.get('step_number', '?')

        # Quick rule-based checks first
        event_type = step.get('event_type', '')

        # Never mark critical actions as redundant
        if event_type in ('open_app', 'launch_app', 'goto', 'navigate'):
            logger.debug(f"[Redundancy:{step_num}] {event_type} is critical, not redundant")
            return RedundancyCheckResult(is_redundant=False)

        if not self.agent_config.allow_strategy_adaptation:
            return RedundancyCheckResult(is_redundant=False)

        logger.info(f"[Redundancy:{step_num}] Checking with Vision LLM")

        result = await self.reasoning_engine.check_redundancy(
            step=step,
            ui_state=ui_state,
            history=self.execution_history
        )

        if result.is_redundant:
            logger.info(f"[Redundancy:{step_num}] Vision LLM marked as redundant: {result.redundancy_type.value}")
        else:
            logger.debug(f"[Redundancy:{step_num}] Not redundant")

        return result

    async def _execute_step_with_adaptation(
        self,
        step: dict[str, Any],
        step_number: int,
        round_config: RoundConfig,
        is_loop_substep: bool = False
    ) -> StepResult:
        """
        Execute a single step with anomaly detection and adaptation

        Args:
            step: The step to execute
            step_number: Step number for tracking
            round_config: Round configuration
            is_loop_substep: If True, this is a sub-step inside a loop (gets redundancy protection)
        """
        start_time = time.time()

        result = StepResult(
            step_number=step_number,
            original_step=step.copy()
        )

        # Capture pre-execution state
        event_type = step.get("event_type", "")
        extract_type = step.get("extract_type", "")
        if event_type in ("open_app", "launch_app"):
            pre_state = {}
        elif event_type in ("wait", "wait_for", "scroll") or extract_type == "gui_extract":
            pre_state = {"skip_capture": True}
        else:
            pre_state = await self.worker.capture_state()
        result.execution = ExecutionDetail(pre_state=pre_state)

        # ===== Redundancy Detection (Agentic) =====
        # Loop sub-steps get redundancy protection (they're usually critical for the workflow)
        if is_loop_substep:
            logger.debug(f"[Validator] Step {step_number}: Loop sub-step, skipping redundancy check")
            redundancy_check = RedundancyCheckResult(is_redundant=False)
        else:
            redundancy_check = await self._check_step_redundancy(step, pre_state, step_number)

        result.redundancy_check = redundancy_check

        if redundancy_check.is_redundant:
            logger.warning(
                f"[Validator] Step {step_number}: Detected as redundant "
                f"({redundancy_check.redundancy_type.value}). Skipping execution."
            )
            result.status = StepExecutionStatus.REDUNDANT
            result.execution_time_ms = 0
            self._redundant_step_numbers.add(step_number)
            self._executed_steps.append(result)
            return result

        # ===== Agentic Reasoning (New Phase 4) =====
        decision = await self.reasoning_engine.decide_next_step(
            current_step=step,
            ui_state=pre_state,
            history=self.execution_history
        )

        logger.info(f"[Validator] Step {step_number} Decision: {decision.action} ({decision.confidence})")
        logger.info(f"[Validator] Reasoning: {decision.reasoning}")

        if decision.action == "skip":
            result.status = StepExecutionStatus.SKIPPED
            result.error_message = f"Agent decided to skip: {decision.reasoning}"
            return result

        if decision.action == "abort":
            result.status = StepExecutionStatus.FAILED
            result.error_message = f"Agent decided to abort: {decision.reasoning}"
            return result

        if decision.action == "correct" or (decision.additional_steps and decision.action != "execute"):
            self.total_anomalies += 1
            # Handle additional steps (e.g., closing a popup)
            for i, add_step in enumerate(decision.additional_steps):
                logger.info(f"[Validator] Executing pre-step {i+1}: {add_step.get('event_type')}")
                await self._execute_step(add_step, round_config)

            # Record adaptation
            adaptation = AdaptationRecord(
                anomaly_type=AnomalyType.UNEXPECTED_FLOW if decision.additional_steps else AnomalyType.COORDINATE_DRIFT,
                original_strategy=step.copy(),
                adapted_strategy=decision.suggested_step or step,
                reasoning=decision.reasoning,
                success=True,
                additional_steps=decision.additional_steps
            )
            result.adaptations.append(adaptation)

            # Record for evolution (Phase 4)
            evolved_step = self._sanitize_step_for_evolution(decision.suggested_step, step) if decision.suggested_step else step.copy()
            sanitized_additional = [self._sanitize_step_for_evolution(s) for s in (decision.additional_steps or [])]
            self.evolution_records.append(MacroEvolutionRecord(
                original_step=step.copy(),
                evolved_step=evolved_step,
                evolution_reason=f"Agent Choice: {decision.reasoning}",
                confidence=decision.confidence,
                additional_steps=sanitized_additional
            ))

            result.effective_parameters = adaptation.adapted_strategy
            step = adaptation.adapted_strategy  # Use corrected step
            self.total_adaptations += 1

        # Execute the step (original or adapted)
        # Special handling for loop steps - validate sub-steps individually
        if step.get("type") == "loop":
            execution_result = await self._execute_loop_with_adaptation(
                step=step,
                step_number=step_number,
                round_config=round_config,
                result=result
            )
        else:
            execution_result = await self._execute_step(step, round_config)
        result.execution.action_taken = step

        # Capture post-execution state (skip for wait/scroll/extract, lightweight for open_app)
        extract_type = step.get("extract_type", "")
        if event_type in ("wait", "wait_for", "scroll") or extract_type == "gui_extract":
            post_state = {"skip_capture": True}  # No need to capture
        elif event_type in ("open_app", "launch_app"):
            post_state = await self._capture_app_state_only()
        else:
            post_state = await self.worker.capture_state()
        result.execution.post_state = post_state

        # ===== Visual Outcome Verification (New Phase 4) =====
        # Skip visual verification for parent loop step (it's verified via sub-steps)
        if step.get("type") == "loop":
            is_verified, verification_reason = True, "Loop validated via sub-steps"
        else:
            is_verified, verification_reason = await self.reasoning_engine.verify_outcome(
                step=step,
                pre_state=pre_state,
                post_state=post_state
            )

        logger.info(f"[Validator] Step {step_number} Verification: {'SUCCESS' if is_verified else 'FAILED'}")
        logger.info(f"[Validator] Verification Reason: {verification_reason}")

        if not is_verified:
            # If visual verification fails, treat as an anomaly and attempt one agentic retry
            self.total_anomalies += 1
            logger.warning(f"[Validator] Step {step_number}: Visual verification failed. Attempting recovery.")

            # Use reasoning engine for recovery decision
            recovery_decision = await self.reasoning_engine.decide_next_step(
                current_step=step,
                ui_state=post_state,  # Use post-state for recovery context
                history=self.execution_history,
                is_recovery=True,
                failure_reason=verification_reason
            )

            logger.info(f"[Validator] Step {step_number} Recovery Decision: action={recovery_decision.action}, confidence={recovery_decision.confidence}")
            logger.info(f"[Validator] Recovery Reasoning: {recovery_decision.reasoning}")
            if recovery_decision.additional_steps:
                logger.info(f"[Validator] Recovery includes {len(recovery_decision.additional_steps)} additional steps")

            if recovery_decision.action == "correct":
                # Execute recovery steps
                for i, add_step in enumerate(recovery_decision.additional_steps):
                    await self._execute_step(add_step, round_config)

                # Retry main step
                retry_result = await self._execute_step(recovery_decision.suggested_step or step, round_config)
                if not self._has_engine_error(retry_result):
                    result.status = StepExecutionStatus.ADAPTED
                    # Record adaptation
                    adaptation = AdaptationRecord(
                        anomaly_type=AnomalyType.STATE_MISMATCH,
                        original_strategy=step.copy(),
                        adapted_strategy=recovery_decision.suggested_step or step,
                        reasoning=f"Recovery from verification failure: {verification_reason}. Agent reasoning: {recovery_decision.reasoning}",
                        success=True
                    )
                    result.adaptations.append(adaptation)

                    # Record for evolution
                    evolved_step = self._sanitize_step_for_evolution(recovery_decision.suggested_step, step) if recovery_decision.suggested_step else step.copy()
                    sanitized_additional = [self._sanitize_step_for_evolution(s) for s in (recovery_decision.additional_steps or [])]
                    self.evolution_records.append(MacroEvolutionRecord(
                        original_step=step.copy(),
                        evolved_step=evolved_step,
                        evolution_reason=f"Agent Recovery: {recovery_decision.reasoning}",
                        confidence=recovery_decision.confidence,
                        additional_steps=sanitized_additional
                    ))
                else:
                    result.status = StepExecutionStatus.FAILED
                    result.error_message = f"Recovery attempt failed: {recovery_decision.reasoning}"
            else:
                result.status = StepExecutionStatus.FAILED
                result.error_message = f"Visual verification failed: {verification_reason}. Recovery action: {recovery_decision.action}"
                logger.warning(f"[Validator] Step {step_number}: Recovery not attempted or failed. Action={recovery_decision.action}")
        else:
            # Visual verification passed or skipped
            if not self._has_engine_error(execution_result):
                result.status = StepExecutionStatus.PASSED
            else:
                result.status = StepExecutionStatus.FAILED
                result.error_message = str(execution_result.get("error", "Engine execution failed"))

        result.execution_time_ms = int((time.time() - start_time) * 1000)

        # 记录已执行的步骤，用于后续冗余检测
        self._executed_steps.append(result)

        return result

    async def _execute_loop_with_adaptation(
        self,
        step: dict[str, Any],
        step_number: int,
        round_config: RoundConfig,
        result: StepResult
    ) -> dict[str, Any]:
        """
        Execute a loop step with anomaly detection and adaptation for sub-steps.

        This method validates each sub-step individually, applying the same
        anomaly detection and adaptation logic as top-level steps.
        """
        import asyncio

        sub_steps = step.get("steps", [])
        max_iterations = step.get("max_iterations", 50)
        loop_results = []
        sub_step_adaptations = []

        logger.info(f"[Validator] Executing loop with {len(sub_steps)} sub-steps with validation")

        # For verification, execute only 1 iteration
        iterations = 1

        for iteration in range(iterations):
            logger.info(f"[Validator] Loop iteration {iteration + 1}/{iterations}")
            iteration_results = []

            for sub_idx, sub_step in enumerate(sub_steps):
                # Use integer step number for sub-steps (e.g., 501 for step 5.1)
                sub_step_num = step_number * 100 + sub_idx + 1
                logger.info(f"[Validator] Validating sub-step {step_number}.{sub_idx + 1} (id: {sub_step_num})")

                # Add step_number to sub_step for evolution record matching
                sub_step_copy = sub_step.copy()
                sub_step_copy["step_number"] = sub_step_num

                # Execute sub-step with adaptation (mark as loop sub-step for redundancy protection)
                sub_result = await self._execute_step_with_adaptation(
                    step=sub_step_copy,
                    step_number=sub_step_num,
                    round_config=round_config,
                    is_loop_substep=True
                )

                iteration_results.append({
                    "step": sub_step.get("step_number", sub_idx + 1),
                    "status": sub_result.status.value,
                    "adaptations": len(sub_result.adaptations),
                    "result": sub_result
                })

                # Collect adaptations from sub-step
                if sub_result.adaptations:
                    sub_step_adaptations.extend(sub_result.adaptations)
                    result.adaptations.extend(sub_result.adaptations)

                # Check if sub-step failed
                if sub_result.status == StepExecutionStatus.FAILED:
                    logger.warning(f"[Validator] Sub-step {sub_step_num} failed: {sub_result.error_message}")

                # Small delay between sub-steps
                await asyncio.sleep(0.5)

            loop_results.append({
                "iteration": iteration + 1,
                "steps": iteration_results
            })

        logger.info(f"[Validator] Loop completed with {len(sub_step_adaptations)} sub-step adaptations")

        return {
            "status": "completed",
            "iterations": len(loop_results),
            "results": loop_results,
            "sub_step_adaptations": len(sub_step_adaptations)
        }

    async def _capture_app_state_only(self) -> dict[str, Any]:
        """
        Lightweight state capture for app launch - only package name, no UI dump or screenshot.
        Much faster than full capture_state().
        """
        state = {
            "platform": self.worker.config.platform if self.worker else None,
            "timestamp": time.time(),
            "elements": [],
            "screenshot": None,
            "current_activity": None,
            "package_name": None,
        }

        try:
            if self.worker.config.platform == "android":
                from app.core.environment.controllers.mobile_controller import (
                    MobileController,
                )
                current_app = await MobileController.get_current_app_cached(
                    self.worker.config.device_id
                )
                state["current_activity"] = current_app.get("activity")
                state["package_name"] = current_app.get("package")
        except Exception as e:
            logger.warning(f"[Validator] Failed to capture app state: {e}")

        return state

    async def _execute_step(
        self,
        step: dict[str, Any],
        config: RoundConfig,
        step_validator: Any | None = None
    ) -> Any:
        """Execute a single step through the worker"""
        try:
            # For loop steps, pass the step_validator for sub-step validation
            if step.get("type") == "loop" and step_validator:
                return await asyncio.wait_for(
                    self.worker.execute_step(step, step_validator=step_validator),
                    timeout=config.timeout_per_step
                )
            else:
                return await asyncio.wait_for(
                    self.worker.execute_step(step),
                    timeout=config.timeout_per_step
                )
        except asyncio.TimeoutError:
            return {"error": "timeout", "message": f"Step timed out after {config.timeout_per_step}s"}
        except Exception as e:
            return {"error": "execution_failed", "message": str(e)}

    def _has_engine_error(self, result: Any) -> bool:
        """Check if execution result indicates a low-level engine error"""
        if result is None:
            return False

        if isinstance(result, dict):
            return "error" in result or "failed" in str(result).lower()

        if isinstance(result, str):
            error_keywords = ["error", "failed", "timeout", "not found", "exception"]
            return any(kw in result.lower() for kw in error_keywords)

        return False

    def _sanitize_step_for_evolution(self, step: dict[str, Any], original_step: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Ensure step has all required fields for MacroScript validation.
        Fixes None values for list fields that cause Pydantic validation errors.
        """
        if not step:
            return step

        sanitized = step.copy()

        # Ensure list fields are lists (not None)
        for key in ["then_steps", "else_steps", "steps"]:
            if not sanitized.get(key):  # Handles None, missing, or empty
                if original_step and original_step.get(key):
                    sanitized[key] = original_step.get(key)
                else:
                    sanitized[key] = []

        # Ensure max_iterations has a value
        if not sanitized.get("max_iterations"):
            if original_step and original_step.get("max_iterations"):
                sanitized["max_iterations"] = original_step.get("max_iterations")
            else:
                sanitized["max_iterations"] = 50

        return sanitized

    async def _should_continue_after_failure(self, step_result: StepResult) -> bool:
        """
        Determine if verification should continue after step failure.
        Delegates reasoning to the Agent to avoid hardcoded rules.
        """
        step_num = step_result.step_number

        # If conservative mode is off, we generally try to continue
        if not self.agent_config.conservative_mode:
            logger.warning(f"[Validator] Step {step_num} FAILED but continuing (conservative_mode=False)")
            return True

        # Ask the reasoning engine if this failure is terminal
        # This is a lightweight reasoning step
        if self.worker:
            is_terminal = await self.reasoning_engine.is_failure_terminal(
                step=step_result.original_step,
                error=step_result.error_message or "Unknown error"
            )
            should_continue = not is_terminal
            logger.info(f"[Validator] Step {step_num} terminal analysis: is_terminal={is_terminal}, continue={should_continue}")
            return should_continue

        logger.warning(f"[Validator] Step {step_num} FAILED, no worker available, stopping")
        return False

    async def _build_response(self) -> VerificationResponse:
        """Build final verification response"""
        # 1. Build evolved macro (also generates optimization stats implicitly)
        evolved_macro, optimization_stats = self._build_evolved_macro()

        # 2. Generate agentic report (this also populates self._analysis_result)
        report = await self._generate_agentic_report()

        return VerificationResponse(
            success=self._determine_overall_status() == VerificationStatus.COMPLETED,
            status=self._determine_overall_status(),
            evolved_macro=evolved_macro,
            execution_mode=self._analysis_result.recommended_execution_mode,
            confidence_score=self._analysis_result.confidence_score,
            verification_report=report,
            evolution_records=self.evolution_records,
            processing_time_seconds=time.time() - (self.start_time or time.time()),
            rounds_completed=len(self.round_reports)
        )

    async def _generate_agentic_report(self) -> VerificationReport:
        """Generate a qualitative report using Agent reasoning"""
        analysis = await self.reasoning_engine.analyze_results(
            reports=self.round_reports,
            macro_script=self.current_macro
        )

        # Calculate quantitative summary for reference
        summary = self._calculate_basic_summary()
        summary.total_anomalies_detected = self.total_anomalies
        summary.total_adaptations_applied = self.total_adaptations

        # Store for response
        self._analysis_result = analysis

        return VerificationReport(
            summary=summary,
            rounds=self.round_reports,
            issues=analysis.issues,
            recommendations=analysis.recommendations,
            qualitative_assessment=analysis.qualitative_assessment
        )

    def _calculate_basic_summary(self) -> ReportSummary:
        """Calculate basic statistics for the summary"""
        total_steps = sum(r.total_steps for r in self.round_reports)
        passed_steps = sum(r.passed_steps for r in self.round_reports)

        # Calculate average execution time from all step results
        total_time_ms = 0
        step_count = 0
        for round_report in self.round_reports:
            for step_result in round_report.step_results:
                total_time_ms += step_result.execution_time_ms
                step_count += 1
        average_time = int(total_time_ms / max(step_count, 1))

        return ReportSummary(
            overall_success_rate=passed_steps / max(total_steps, 1),
            average_execution_time_ms=average_time
        )

    def _build_evolved_macro(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Build evolved macro using MacroEvolutionEngine (Phase 3)

        Transforms adaptations into structural macro enhancements with:
        - Fallback mechanisms
        - Error handling
        - Optimization
        - Redundancy removal

        Returns:
            Tuple of (evolved_macro, optimization_stats)
        """
        # Phase 0: Filter out redundant steps identified during verification
        filtered_macro = self._filter_redundant_steps_from_macro(self.current_macro)

        if not self.evolution_records and not self._redundant_step_numbers:
            logger.info("[Validator] No evolution records or redundant steps found")
            # Just optimize the filtered macro directly
            evolved_macro = filtered_macro
        else:
            if self._redundant_step_numbers:
                logger.info(f"[Validator] Building evolved macro with {len(self.evolution_records)} corrections and {len(self._redundant_step_numbers)} redundant steps removed")
            else:
                logger.info(f"[Validator] Building evolved macro with {len(self.evolution_records)} records")

        # Collect all step results from all rounds
        all_step_results: list[StepResult] = []
        for round_report in self.round_reports:
            all_step_results.extend(round_report.step_results)

        # Determine target platform
        target_platform = self.request.target_environment.platform

        # Phase 3: Use MacroEvolutionEngine on filtered macro
        engine = MacroEvolutionEngine()
        evolved_macro, metadata = engine.evolve(
            original_macro=filtered_macro,
            evolution_records=self.evolution_records,
            step_results=all_step_results,
            target_platform=target_platform
        )

        logger.info(
            f"[Validator] Macro evolved: {metadata['original_step_count']} -> "
            f"{metadata['evolved_step_count']} steps "
            f"({metadata['expansion_ratio']:.2f}x expansion)"
        )

        # Phase 3b: Optimize the evolved macro using full MacroOptimizer
        from app.core.execution.macro.schemas import MacroScript
        optimizer = MacroOptimizer(enable_all_strategies=True)
        script = MacroScript(steps=evolved_macro)
        optimized_script, stats = optimizer.optimize(script)

        if stats.reduction_ratio > 0:
            logger.info(
                f"[Validator] MacroOptimizer reduced steps: {stats.original_steps} -> {stats.optimized_steps} "
                f"({stats.reduction_ratio*100:.1f}% reduction, saved {stats.time_saved_ms}ms)"
            )
            if stats.removed_steps > 0:
                logger.info(f"[Validator] Removed {stats.removed_steps} redundant steps")
            if stats.merged_steps > 0:
                logger.info(f"[Validator] Merged {stats.merged_steps} steps")

        # Convert back to list format
        optimized_macro = [step.model_dump() if hasattr(step, 'model_dump') else step for step in optimized_script.steps]

        return optimized_macro, stats.__dict__ if hasattr(stats, '__dict__') else None

    def _filter_redundant_steps_from_macro(
        self,
        macro: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        从宏中过滤掉被标记为冗余的步骤（包括 loop 内的子步骤）
        """
        if not self._redundant_step_numbers:
            return macro

        filtered = []
        removed_count = 0

        for idx, step in enumerate(macro, 1):
            if idx in self._redundant_step_numbers:
                logger.info(f"[Evolution] Removing redundant step {idx}: {step.get('event_type', 'unknown')}")
                removed_count += 1
                continue

            # Handle loop steps - filter redundant sub-steps
            if step.get("type") == "loop":
                sub_steps = step.get("steps", [])
                if sub_steps:
                    filtered_sub_steps = []
                    for sub_idx, sub_step in enumerate(sub_steps):
                        # Calculate sub-step number (e.g., 501 for step 5, sub-step 0)
                        # This MUST match the calculation in _execute_loop_with_adaptation
                        sub_step_num = idx * 100 + sub_idx + 1
                        sub_step_original_num = sub_step.get('step_number', sub_idx + 1)
                        if sub_step_num in self._redundant_step_numbers:
                            logger.info(f"[Evolution] Removing redundant sub-step {sub_step_num} (original: {sub_step_original_num}): {sub_step.get('event_type', 'unknown')}")
                            removed_count += 1
                            continue
                        filtered_sub_steps.append(sub_step)

                    # Update step with filtered sub-steps
                    step = copy.deepcopy(step)
                    step["steps"] = filtered_sub_steps

            filtered.append(step)

        if removed_count > 0:
            logger.info(f"[Evolution] Filtered {removed_count} redundant steps from macro")

        return filtered

    def _determine_overall_status(self) -> VerificationStatus:
        """Determine overall verification status"""
        if not self.round_reports:
            return VerificationStatus.FAILED

        statuses = [r.status for r in self.round_reports]

        if all(s == VerificationStatus.COMPLETED for s in statuses):
            return VerificationStatus.COMPLETED

        if any(s == VerificationStatus.FAILED for s in statuses):
            return VerificationStatus.FAILED

        return VerificationStatus.PARTIAL_FAILED

    def _build_error_response(self, error_message: str) -> VerificationResponse:
        """Build error response"""
        processing_time = time.time() - (self.start_time or time.time())

        return VerificationResponse(
            success=False,
            status=VerificationStatus.FAILED,
            evolved_macro=None,
            execution_mode=ExecutionMode.AGENTIC,
            confidence_score=0.0,
            verification_report=VerificationReport(
                issues=[VerificationIssue(
                    severity="critical",
                    category="verification_error",
                    description=error_message,
                    affected_steps=[]
                )]
            ),
            processing_time_seconds=processing_time,
            rounds_completed=len(self.round_reports),
            error_message=error_message
        )
