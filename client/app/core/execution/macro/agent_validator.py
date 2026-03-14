"""
AgentMacroValidator - Agent-based Macro Verification System

The main orchestrator for active macro verification.
Manages multi-round verification, anomaly detection, and macro evolution.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from app.core.execution.macro.adaptation_library import AdaptationStrategyLibrary
from app.core.execution.macro.anomaly_detector import AnomalyDetector, AnomalyDetectionResult
from app.core.execution.macro.evolution_engine import (
    EvolutionOptimizer,
    MacroEvolutionEngine,
)
from app.core.execution.macro.round_orchestrator import (
    BaselineStrategy,
    ChaosStrategy,
    RoundOrchestrator,
    StressTestStrategy,
)
from app.core.execution.macro.verification_models import (
    AdaptationRecord,
    AgentConfig,
    AnomalyType,
    ExecutionDetail,
    ExecutionMode,
    RoundConfig,
    RoundReport,
    StepExecutionStatus,
    StepResult,
    VerificationIssue,
    VerificationReport,
    VerificationRequest,
    VerificationResponse,
    VerificationStatus,
    MacroEvolutionRecord,
    ReportSummary,
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
        self.agent_config = request.agent_config or AgentConfig()
        self.anomaly_detector = AnomalyDetector()
        self.adaptation_library = AdaptationStrategyLibrary(use_llm=self.agent_config.allow_strategy_adaptation)
        self.worker: Optional[VerificationWorker] = None

        # Phase 4: Round orchestration
        self.orchestrator = self._create_orchestrator()

        # Execution state
        self.execution_history: List[Dict[str, Any]] = []
        self.adaptation_records: List[AdaptationRecord] = []
        self.round_reports: List[RoundReport] = []

        # Evolution tracking
        self.evolution_records: List[MacroEvolutionRecord] = []
        self.current_macro: List[Dict[str, Any]] = request.macro_script.copy()

        # Statistics
        self.total_anomalies = 0
        self.total_adaptations = 0
        self.start_time: Optional[float] = None

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
            return self._build_response()

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
            agent_config=self.agent_config
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
        macro_script: Optional[List[Dict[str, Any]]] = None
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

        step_results: List[StepResult] = []

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

    async def _execute_step_with_adaptation(
        self,
        step: Dict[str, Any],
        step_number: int,
        round_config: RoundConfig
    ) -> StepResult:
        """
        Execute a single step with anomaly detection and adaptation
        """
        start_time = time.time()

        result = StepResult(
            step_number=step_number,
            original_step=step.copy()
        )

        # Capture pre-execution state
        pre_state = await self.worker.capture_state()
        result.execution = ExecutionDetail(pre_state=pre_state)

        # Pre-execution anomaly detection
        pre_anomaly = await self.anomaly_detector.detect_pre_execution_anomaly(
            step=step,
            current_ui_state=pre_state
        )

        if pre_anomaly.is_anomaly:
            self.total_anomalies += 1
            logger.info(
                f"[Validator] Step {step_number}: Pre-execution anomaly detected: "
                f"{pre_anomaly.anomaly_type}"
            )

            # Attempt adaptation
            adapted = await self._attempt_adaptation(
                step=step,
                anomaly=pre_anomaly,
                step_number=step_number
            )

            if adapted.success:
                result.adaptations.append(adapted)
                result.effective_parameters = adapted.adapted_strategy
                step = adapted.adapted_strategy  # Use adapted step
                self.total_adaptations += 1
            else:
                result.status = StepExecutionStatus.FAILED
                result.error_message = f"Pre-execution anomaly not resolved: {pre_anomaly.anomaly_type}"
                result.execution_time_ms = int((time.time() - start_time) * 1000)
                return result

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

        # Capture post-execution state
        post_state = await self.worker.capture_state()
        result.execution.post_state = post_state

        # Post-execution anomaly detection
        post_anomaly = await self.anomaly_detector.detect_post_execution_anomaly(
            step=step,
            pre_state=pre_state,
            post_state=post_state,
            execution_result=execution_result
        )

        if post_anomaly.is_anomaly:
            self.total_anomalies += 1
            logger.info(
                f"[Validator] Step {step_number}: Post-execution anomaly detected: "
                f"{post_anomaly.anomaly_type}"
            )

            # Attempt post-execution adaptation
            adapted = await self._attempt_adaptation(
                step=step,
                anomaly=post_anomaly,
                step_number=step_number,
                is_post_execution=True
            )

            if adapted.success:
                result.adaptations.append(adapted)
                self.total_adaptations += 1
                # Retry the step with adapted strategy
                retry_result = await self._execute_step(adapted.adapted_strategy, round_config)
                if self._is_successful_execution(retry_result):
                    result.status = StepExecutionStatus.ADAPTED
                else:
                    result.status = StepExecutionStatus.FAILED
                    result.error_message = "Adaptation retry failed"
            else:
                # Check if execution was still successful despite anomaly warning
                if self._is_successful_execution(execution_result):
                    result.status = StepExecutionStatus.PASSED
                else:
                    result.status = StepExecutionStatus.FAILED
                    result.error_message = f"Post-execution anomaly: {post_anomaly.anomaly_type}"
        else:
            # No anomaly, check execution result
            if self._is_successful_execution(execution_result):
                result.status = StepExecutionStatus.PASSED
            else:
                result.status = StepExecutionStatus.FAILED
                result.error_message = str(execution_result) if execution_result else "Execution failed"

        result.execution_time_ms = int((time.time() - start_time) * 1000)
        return result

    async def _execute_loop_with_adaptation(
        self,
        step: Dict[str, Any],
        step_number: int,
        round_config: RoundConfig,
        result: StepResult
    ) -> Dict[str, Any]:
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
                logger.debug(f"[Validator] Validating sub-step {step_number}.{sub_idx + 1} (id: {sub_step_num})")

                # Add step_number to sub_step for evolution record matching
                sub_step_copy = sub_step.copy()
                sub_step_copy["step_number"] = sub_step_num

                # Execute sub-step with adaptation
                sub_result = await self._execute_step_with_adaptation(
                    step=sub_step_copy,
                    step_number=sub_step_num,
                    round_config=round_config
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

    async def _execute_step(
        self,
        step: Dict[str, Any],
        config: RoundConfig,
        step_validator: Optional[Any] = None
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

    async def _attempt_adaptation(
        self,
        step: Dict[str, Any],
        anomaly: AnomalyDetectionResult,
        step_number: int,
        is_post_execution: bool = False,
        ui_state: Optional[Dict[str, Any]] = None
    ) -> AdaptationRecord:
        """
        Attempt to adapt strategy based on detected anomaly using the adaptation library.

        Implements two-tier adaptation:
        1. Quick fix (heuristics-based)
        2. LLM deep adaptation (if quick fix fails and config allows)
        """
        # Get current UI state if not provided
        if ui_state is None and self.worker:
            ui_state = await self.worker.capture_state()

        # Use adaptation library with fallback
        records = await self.adaptation_library.adapt_with_fallback(
            step=step,
            anomaly_type=anomaly.anomaly_type,
            anomaly_details=anomaly.details,
            ui_state=ui_state,
            max_attempts=self.agent_config.max_retries_per_step
        )

        # Use the last (most evolved) record as the primary result
        primary_record = records[-1] if records else AdaptationRecord(
            anomaly_type=anomaly.anomaly_type,
            original_strategy=step,
            adapted_strategy=step,
            reasoning="No adaptation attempts made",
            success=False,
            attempt_number=1
        )

        # Store all adaptation records
        self.adaptation_records.extend(records)

        # Record for evolution if successful
        if primary_record.success:
            self.evolution_records.append(MacroEvolutionRecord(
                original_step=step,
                evolved_step=primary_record.adapted_strategy,
                evolution_reason=f"Phase 2: {primary_record.reasoning}",
                confidence=anomaly.confidence
            ))
            self.total_adaptations += 1

        return primary_record

    def _is_successful_execution(self, result: Any) -> bool:
        """Check if execution result indicates success"""
        if result is None:
            return True  # Void operation

        if isinstance(result, dict):
            return "error" not in result and "failed" not in str(result).lower()

        if isinstance(result, str):
            error_keywords = ["error", "failed", "timeout", "not found", "exception"]
            return not any(kw in result.lower() for kw in error_keywords)

        return True

    async def _should_continue_after_failure(self, step_result: StepResult) -> bool:
        """Determine if verification should continue after step failure"""
        # Continue if this is not a critical step (can be determined by step metadata)
        original_step = step_result.original_step

        # Critical steps are typically navigation or app transitions
        event_type = original_step.get("event_type", "")
        critical_types = ["goto", "navigate", "open_app", "launch_app"]

        if event_type in critical_types:
            return False

        # Continue if configured to be lenient
        if not self.agent_config.conservative_mode:
            return True

        return False

    def _build_response(self) -> VerificationResponse:
        """Build final verification response"""
        processing_time = time.time() - (self.start_time or time.time())

        # Generate report
        report = self._generate_report()

        # Determine execution mode
        execution_mode = self._determine_execution_mode()

        # Build evolved macro
        evolved_macro = self._build_evolved_macro()

        # Calculate confidence score
        confidence_score = self._calculate_confidence_score()

        return VerificationResponse(
            success=report.summary.overall_success_rate >= 0.7,
            status=self._determine_overall_status(),
            evolved_macro=evolved_macro,
            execution_mode=execution_mode,
            confidence_score=confidence_score,
            verification_report=report,
            evolution_records=self.evolution_records,
            processing_time_seconds=processing_time,
            rounds_completed=len(self.round_reports)
        )

    def _generate_report(self) -> VerificationReport:
        """Generate detailed verification report"""
        # Calculate statistics
        total_steps = sum(r.total_steps for r in self.round_reports)
        passed_steps = sum(r.passed_steps for r in self.round_reports)
        adapted_steps = sum(r.adapted_steps for r in self.round_reports)
        failed_steps = sum(r.failed_steps for r in self.round_reports)

        success_rate = passed_steps / max(total_steps, 1)
        adaptation_rate = adapted_steps / max(total_steps, 1)

        # Calculate round variance
        round_success_rates = [
            r.passed_steps / max(r.total_steps, 1)
            for r in self.round_reports
        ]
        max_variance = max(round_success_rates) - min(round_success_rates) if len(round_success_rates) > 1 else 0

        summary = ReportSummary(
            overall_success_rate=success_rate,
            adaptation_rate=adaptation_rate,
            max_round_variance=max_variance,
            average_execution_time_ms=sum(
                sum(s.execution_time_ms for s in r.step_results)
                for r in self.round_reports
            ) // max(total_steps, 1),
            total_anomalies_detected=self.total_anomalies,
            total_adaptations_applied=self.total_adaptations
        )

        # Generate issues
        issues = self._identify_issues()

        # Generate recommendations
        recommendations = self._generate_recommendations(summary, issues)

        return VerificationReport(
            summary=summary,
            rounds=self.round_reports,
            issues=issues,
            recommendations=recommendations
        )

    def _identify_issues(self) -> List[VerificationIssue]:
        """Identify issues from verification results"""
        issues = []

        # Group failures by type
        failure_patterns: Dict[str, List[int]] = {}

        for round_report in self.round_reports:
            for step_result in round_report.step_results:
                if step_result.status == StepExecutionStatus.FAILED:
                    error = step_result.error_message or "unknown"
                    pattern = error.split(":")[0] if ":" in error else error

                    if pattern not in failure_patterns:
                        failure_patterns[pattern] = []
                    failure_patterns[pattern].append(step_result.step_number)

        # Create issues from patterns
        for pattern, affected_steps in failure_patterns.items():
            severity = "critical" if len(affected_steps) > 2 else "warning"
            issues.append(VerificationIssue(
                severity=severity,
                category=pattern,
                description=f"Recurring failure pattern: {pattern}",
                affected_steps=affected_steps,
                suggestion=f"Consider adding fallback strategy for {pattern}"
            ))

        # Check for high variance between rounds
        if len(self.round_reports) > 1:
            rates = [r.passed_steps / max(r.total_steps, 1) for r in self.round_reports]
            if max(rates) - min(rates) > 0.3:
                issues.append(VerificationIssue(
                    severity="warning",
                    category="instability",
                    description="High variance between verification rounds indicates instability",
                    affected_steps=[],
                    suggestion="Consider adding more robust waits or state verification"
                ))

        return issues

    def _generate_recommendations(
        self,
        summary: ReportSummary,
        issues: List[VerificationIssue]
    ) -> List[str]:
        """Generate recommendations based on verification results"""
        recommendations = []

        if summary.adaptation_rate > 0.3:
            recommendations.append(
                "High adaptation rate detected. Consider evolving the macro with the applied adaptations."
            )

        if summary.overall_success_rate < 0.8:
            recommendations.append(
                "Success rate below 80%. Recommend using Hybrid or Agentic execution mode."
            )

        if summary.total_anomalies_detected > len(self.current_macro) * 0.5:
            recommendations.append(
                "Many anomalies detected. The UI may be dynamic or unpredictable. "
                "Consider using more robust selectors or Agentic execution."
            )

        if any(i.severity == "critical" for i in issues):
            recommendations.append(
                "Critical issues found. Manual review recommended before deployment."
            )

        return recommendations

    def _determine_execution_mode(self) -> ExecutionMode:
        """Determine recommended execution mode based on verification results"""
        if not self.round_reports:
            return ExecutionMode.AGENTIC

        # Calculate metrics
        total_adapted = sum(r.adapted_steps for r in self.round_reports)
        total_failed = sum(r.failed_steps for r in self.round_reports)
        total_steps = sum(r.total_steps for r in self.round_reports)

        adaptation_rate = total_adapted / max(total_steps, 1)
        failure_rate = total_failed / max(total_steps, 1)

        # Determine mode
        if failure_rate == 0 and adaptation_rate == 0:
            # Perfect execution
            return ExecutionMode.DETERMINISTIC

        if adaptation_rate > 0.5 or failure_rate > 0.3:
            # High instability - needs agent intervention
            return ExecutionMode.AGENTIC

        if adaptation_rate > 0 or failure_rate > 0:
            # Some issues but manageable with hybrid approach
            return ExecutionMode.HYBRID

        return ExecutionMode.DETERMINISTIC

    def _build_evolved_macro(self) -> List[Dict[str, Any]]:
        """
        Build evolved macro using MacroEvolutionEngine (Phase 3)

        Transforms adaptations into structural macro enhancements with:
        - Fallback mechanisms
        - Error handling
        - Optimization
        """
        if not self.evolution_records:
            logger.info("[Validator] No evolution records, returning original macro")
            return self.current_macro

        logger.info(f"[Validator] Building evolved macro with {len(self.evolution_records)} records")

        # Collect all step results from all rounds
        all_step_results: List[StepResult] = []
        for round_report in self.round_reports:
            all_step_results.extend(round_report.step_results)

        # Determine target platform
        target_platform = self.request.target_environment.platform

        # Phase 3: Use MacroEvolutionEngine
        engine = MacroEvolutionEngine()
        evolved_macro, metadata = engine.evolve(
            original_macro=self.current_macro,
            evolution_records=self.evolution_records,
            step_results=all_step_results,
            target_platform=target_platform
        )

        logger.info(
            f"[Validator] Macro evolved: {metadata['original_step_count']} -> "
            f"{metadata['evolved_step_count']} steps "
            f"({metadata['expansion_ratio']:.2f}x expansion)"
        )

        # Phase 3b: Optimize the evolved macro
        optimizer = EvolutionOptimizer()
        optimized_macro = optimizer.optimize(evolved_macro)

        if len(optimized_macro) < len(evolved_macro):
            logger.info(
                f"[Validator] Optimization reduced steps: {len(evolved_macro)} -> {len(optimized_macro)}"
            )

        return optimized_macro

    def _calculate_confidence_score(self) -> float:
        """Calculate overall confidence score"""
        if not self.round_reports:
            return 0.0

        # Base score from success rate
        success_rates = [r.passed_steps / max(r.total_steps, 1) for r in self.round_reports]
        base_score = sum(success_rates) / len(success_rates)

        # Penalty for adaptations needed
        adaptation_penalty = min(self.total_adaptations / max(len(self.current_macro), 1) * 0.1, 0.2)

        # Penalty for anomalies
        anomaly_penalty = min(self.total_anomalies / max(len(self.current_macro), 1) * 0.05, 0.1)

        # Consistency bonus
        consistency_bonus = 0.1 if len(success_rates) > 1 and max(success_rates) - min(success_rates) < 0.2 else 0

        score = base_score - adaptation_penalty - anomaly_penalty + consistency_bonus
        return max(0.0, min(1.0, score))

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

