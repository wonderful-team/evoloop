"""
VerificationService - Phase 5: Integration Layer

High-level service for integrating agent-based verification with:
- MacroService (execution)
- SkillSynthesizer (learning)
- External API endpoints
"""

import logging
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from app.core.execution.macro import (
    AgentMacroValidator,
    EnvironmentConfig,
    VerificationRequest,
    VerificationReporter,
)
from app.core.execution.macro.schema import MacroScript, MacroStep
from app.core.execution.macro.service import MacroService, MacroRunResult
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.yaml import macro_from_yaml


class VerificationSummary(DynamicBaseModel):
    success_rate: float
    adaptation_rate: float
    anomalies_detected: int
    adaptations_applied: int


class VerificationIssueOut(DynamicBaseModel):
    severity: str
    category: str
    description: str
    affected_steps: list[Union[int, str]] = Field(default_factory=list)


class VerificationReportOut(DynamicBaseModel):
    summary: VerificationSummary
    issues: list[VerificationIssueOut] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class MacroVerificationResult(DynamicBaseModel):
    success: bool
    status: Optional[str] = None
    execution_mode: Optional[str] = None
    confidence_score: Optional[float] = None
    rounds_completed: Optional[int] = None
    evolved_macro: Optional[list[dict[str, Any]]] = None
    verification_report: Optional[VerificationReportOut] = None
    markdown_report: Optional[str] = None
    error: Optional[str] = None


class ModeRecommendation(DynamicBaseModel):
    can_execute: bool
    recommended_mode: str
    reason: str
    confidence: float


class MacroEvolutionResult(DynamicBaseModel):
    success: bool
    original_macro: Union[list[dict[str, Any]], MacroScript, str]
    evolved_macro: Optional[list[dict[str, Any]]] = None
    execution_mode: Optional[str] = None
    confidence: Optional[float] = None
    improvements: list[str] = Field(default_factory=list)
    report: Optional[VerificationReportOut] = None
    error: Optional[str] = None


class SynthesisVerificationResult(DynamicBaseModel):
    status: str
    evolved_macro: Optional[list[dict[str, Any]]] = None
    execution_mode: Optional[str] = None
    confidence: Optional[float] = None
    report: Optional[VerificationReportOut] = None
    error: Optional[str] = None



logger = logging.getLogger(__name__)


class VerificationService:
    """
    High-level service for macro verification.

    Provides simplified API for common verification scenarios.
    Integrates with existing MacroService and SkillSynthesizer.
    """

    @classmethod
    async def verify_macro(
        cls,
        macro_script: Union[List[MacroStep], MacroScript, str],
        platform: str = "web",
        max_rounds: int = 2,
        auto_evolve: bool = True,
        thread_id: Optional[str] = None,
        stop_on_failure: bool = True
    ) -> MacroVerificationResult:
        """
        Verify a macro script with optional evolution.

        Args:
            macro_script: The macro script to verify (list, MacroScript, or YAML string)
            platform: Target platform (web, android, desktop)
            max_rounds: Number of verification rounds
            auto_evolve: Whether to evolve the macro based on results
            thread_id: Optional thread ID for tracking
            stop_on_failure: If True, stop verification when a step fails.
                            If False, continue to next step after failure.

        Returns:
            Dictionary with verification results and evolved macro
        """
        # Convert various formats to list of steps
        steps = None
        if isinstance(macro_script, MacroScript):
            steps = list(macro_script.steps)
        elif isinstance(macro_script, str):
            # Parse YAML string
            try:
                steps = [MacroStep.model_validate(s) for s in macro_from_yaml(macro_script)]
            except Exception as e:
                logger.error(f"Failed to parse macro YAML: {e}")
                return MacroVerificationResult(
                    success=False,
                    error=f"Invalid macro YAML: {e}",
                    evolved_macro=None,
                    execution_mode="agentic"
                )
        else:
            steps = macro_script

        if not steps:
            return MacroVerificationResult(
                success=False,
                error="Empty macro script",
                evolved_macro=None,
                execution_mode="agentic"
            )

        # Build verification request with agent config
        from app.core.execution.macro.verification_models import VerificationAgentConfig as AgentConfig
        agent_config = AgentConfig(conservative_mode=stop_on_failure)

        request = VerificationRequest(
            macro_script=steps,
            target_environment=EnvironmentConfig(platform=platform),
            max_rounds=max_rounds,
            output_mode="evolved" if auto_evolve else "report_only",
            agent_config=agent_config
        )

        if thread_id:
            request.thread_id = thread_id

        logger.info(
            f"[VerificationService] Starting verification: {len(steps)} steps, "
            f"{max_rounds} rounds, platform={platform}"
        )

        try:
            # Execute verification
            validator = AgentMacroValidator(request)
            response = await validator.validate()

            # Generate report
            reporter = VerificationReporter(response)

            # Build result
            result = MacroVerificationResult(
                success=response.success,
                status=response.status.value,
                execution_mode=response.execution_mode.value,
                confidence_score=response.confidence_score,
                rounds_completed=response.rounds_completed,
                evolved_macro=response.evolved_macro if auto_evolve else None,
                verification_report=VerificationReportOut(
                    summary=VerificationSummary(
                        success_rate=response.verification_report.summary.overall_success_rate,
                        adaptation_rate=response.verification_report.summary.adaptation_rate,
                        anomalies_detected=response.verification_report.summary.total_anomalies_detected,
                        adaptations_applied=response.verification_report.summary.total_adaptations_applied,
                    ),
                    issues=[
                        VerificationIssueOut(
                            severity=issue.severity,
                            category=issue.category,
                            description=issue.description,
                            affected_steps=list(issue.affected_steps)
                        )
                        for issue in response.verification_report.issues
                    ],
                    recommendations=list(response.verification_report.recommendations)
                ),
                markdown_report=reporter.to_markdown(),
            )

            logger.info(
                f"[VerificationService] Verification complete: "
                f"success={response.success}, mode={response.execution_mode.value}, "
                f"confidence={response.confidence_score:.2%}"
            )

            return result

        except Exception as e:
            logger.error(f"[VerificationService] Verification failed: {e}", exc_info=True)
            return MacroVerificationResult(
                success=False,
                error=str(e),
                evolved_macro=None,
                execution_mode="agentic"
            )

    @classmethod
    async def verify_and_select_mode(
        cls,
        macro_script: Union[List[MacroStep], MacroScript],
        platform: str = "web",
        confidence_threshold: float = 0.8
    ) -> ModeRecommendation:
        """
        Verify macro and return recommended execution mode.

        This is a quick check to determine if a macro can run deterministically
        or needs agent supervision.

        Args:
            macro_script: The macro script to verify
            platform: Target platform
            confidence_threshold: Minimum confidence for deterministic mode

        Returns:
            Dictionary with execution mode recommendation
        """
        result = await cls.verify_macro(
            macro_script=macro_script,
            platform=platform,
            max_rounds=1,  # Single round for quick check
            auto_evolve=False
        )

        if not result["success"]:
            return ModeRecommendation(
                can_execute=False,
                recommended_mode="agentic",
                reason=result.get("error", "Verification failed"),
                confidence=0.0
            )

        confidence = result["confidence_score"]

        if confidence >= confidence_threshold and result["status"] == "completed":
            return ModeRecommendation(
                can_execute=True,
                recommended_mode="deterministic",
                reason=f"High confidence ({confidence:.2%}) with no failures",
                confidence=confidence
            )
        elif confidence >= 0.5:
            return ModeRecommendation(
                can_execute=True,
                recommended_mode="hybrid",
                reason=f"Moderate confidence ({confidence:.2%}), some adaptations needed",
                confidence=confidence
            )
        else:
            return ModeRecommendation(
                can_execute=True,
                recommended_mode="agentic",
                reason=f"Low confidence ({confidence:.2%}), agent supervision recommended",
                confidence=confidence
            )

    @classmethod
    async def evolve_macro(
        cls,
        macro_script: Union[List[MacroStep], MacroScript, str],
        platform: str = "web",
        max_rounds: int = 2
    ) -> MacroEvolutionResult:
        """
        Evolve a macro through verification and adaptation.

        Returns the evolved macro with enhanced error handling.

        Args:
            macro_script: Original macro script (list, MacroScript, or YAML string)
            platform: Target platform
            max_rounds: Number of verification rounds

        Returns:
            Dictionary with evolved macro and evolution metadata
        """
        result = await cls.verify_macro(
            macro_script=macro_script,
            platform=platform,
            max_rounds=max_rounds,
            auto_evolve=True
        )

        if not result["success"] or not result["evolved_macro"]:
            return MacroEvolutionResult(
                success=False,
                error=result.get("error", "Evolution failed"),
                original_macro=macro_script,
                evolved_macro=None,
                improvements=[]
            )

        # Calculate improvements
        if isinstance(macro_script, list):
            original_count = len(macro_script)
        elif isinstance(macro_script, MacroScript):
            original_count = len(macro_script.steps)
        elif isinstance(macro_script, str):
            # Parse YAML to count steps
            try:
                steps = macro_from_yaml(macro_script)
                original_count = len(steps)
            except:
                original_count = 0
        else:
            original_count = 0
        evolved_count = len(result["evolved_macro"])

        improvements = []
        report = result.get("verification_report", {})
        summary = report.get("summary", {})

        if summary.get("adaptations_applied", 0) > 0:
            improvements.append(f"Added {summary['adaptations_applied']} error handling mechanisms")

        if evolved_count > original_count:
            improvements.append(f"Expanded {original_count} -> {evolved_count} steps for robustness")

        if summary.get("anomalies_detected", 0) > 0:
            improvements.append(f"Handled {summary['anomalies_detected']} environment anomalies")

        return MacroEvolutionResult(
            success=True,
            original_macro=macro_script,
            evolved_macro=result["evolved_macro"],
            execution_mode=result["execution_mode"],
            confidence=result["confidence_score"],
            improvements=improvements,
            report=result["verification_report"]
        )


class SynthesisIntegration:
    """
    Integration layer for SkillSynthesizer.

    Replaces the old verify_macro method with the new agent-based verification.
    """

    @staticmethod
    async def verify_for_synthesis(
        macro_script: Union[List[Dict[str, Any]], Any],
        thread_id: str,
        project_id: int = 1
    ) -> SynthesisVerificationResult:
        """
        Verify macro during skill synthesis.

        This is the drop-in replacement for the old verify_macro method.

        Args:
            macro_script: Compiled macro from trace (can be list of steps or MacroScript)
            thread_id: Thread ID for context
            project_id: Project ID for environment

        Returns:
            Verification result compatible with old interface
        """
        logger.info(f"[{thread_id}] Phase 5: Running agent-based verification")

        # Normalize macro_script to list of MacroStep instances
        steps = macro_script
        if isinstance(macro_script, MacroScript):
            steps = list(macro_script.steps)

        # Filter out invalid steps (safety check)
        steps = [s for s in steps if isinstance(s, (dict, MacroStep))]

        if not steps:
            logger.error("No valid steps found in macro_script")
            return SynthesisVerificationResult(
                status="failed",
                error="No valid steps in macro script",
                report=None
            )

        # Detect platform from normalized steps
        platform = SynthesisIntegration._detect_platform(steps)

        # Run verification with 2 rounds (baseline + stress test)
        result = await VerificationService.verify_macro(
            macro_script=steps,
            platform=platform,
            max_rounds=2,
            auto_evolve=True,
            thread_id=thread_id
        )

        # Convert to old interface for backwards compatibility
        if result["success"] and result["evolved_macro"]:
            return SynthesisVerificationResult(
                status="success",
                evolved_macro=result["evolved_macro"],
                execution_mode=result["execution_mode"],
                confidence=result["confidence_score"],
                report=result["verification_report"]
            )
        else:
            return SynthesisVerificationResult(
                status="failed",
                error=result.get("error", "Verification failed"),
                report=result.get("verification_report")
            )

    @staticmethod
    def _detect_platform(macro_script: List[MacroStep]) -> str:
        """Detect platform from macro steps (handles nested if/else structures)"""
        sources = set()

        def extract_sources(steps):
            """Recursively extract sources from steps, handling nested structures"""
            for step in steps:
                if not isinstance(step, dict):
                    continue

                # Handle regular action steps
                if "source" in step:
                    sources.add(step["source"])

                # Handle if/else nested steps
                if step.get("type") == "if":
                    # Check condition
                    condition = step.get("condition", {})
                    if isinstance(condition, dict):
                        # Try to infer from condition type
                        cond_type = condition.get("type", "")
                        if "mobile" in str(cond_type).lower():
                            sources.add("mobile")

                    # Recursively process then_steps
                    then_steps = step.get("then_steps", [])
                    if isinstance(then_steps, list):
                        extract_sources(then_steps)

                    # Recursively process else_steps
                    else_steps = step.get("else_steps", [])
                    if isinstance(else_steps, list):
                        extract_sources(else_steps)

        extract_sources(macro_script)

        # Default to "dom" if no sources found
        if not sources:
            sources.add("dom")

        if "mobile" in sources or "android" in sources:
            return "android"
        elif "desktop" in sources:
            return "desktop"
        else:
            return "web"


class MacroServiceIntegration:
    """
    Integration layer for MacroService.

    Adds verification capabilities to macro execution.
    """

    @staticmethod
    async def execute_with_verification(
        thread_id: str,
        macro_script: Union[MacroScript, List[Dict]],
        params: Optional[Dict[str, Any]] = None,
        verify_first: bool = True,
        confidence_threshold: float = 0.7
    ) -> MacroRunResult:
        """
        Execute macro with optional pre-flight verification.

        Args:
            thread_id: Execution thread ID
            macro_script: Macro to execute
            params: Execution parameters
            verify_first: Whether to verify before execution
            confidence_threshold: Minimum confidence to skip agent mode

        Returns:
            Execution result
        """
        if params is None:
            params = {}

        # Pre-flight verification
        if verify_first:
            logger.info(f"[{thread_id}] Running pre-flight verification")

            platform = params.get("platform", "web")
            check = await VerificationService.verify_and_select_mode(
                macro_script=macro_script,
                platform=platform,
                confidence_threshold=confidence_threshold
            )

            logger.info(
                f"[{thread_id}] Verification result: mode={check['recommended_mode']}, "
                f"confidence={check['confidence']:.2%}"
            )

            # If not confident enough, add agent supervision flag
            if check["recommended_mode"] == "agentic":
                params["_require_agent_supervision"] = True
                params["_verification_confidence"] = check["confidence"]

            # Store verification result in params for downstream use
            params["_verification_result"] = check

        return await MacroService.run(thread_id, macro_script, params)


# Convenience functions for direct import

async def verify_macro(
    macro_script: List[MacroStep],
    platform: str = "web",
    max_rounds: int = 2
) -> MacroVerificationResult:
    """
    Quick function to verify a macro.

    Example:
        result = await verify_macro(my_macro, platform="android", max_rounds=3)
        if result["success"]:
            evolved_macro = result["evolved_macro"]
    """
    return await VerificationService.verify_macro(
        macro_script=macro_script,
        platform=platform,
        max_rounds=max_rounds,
        auto_evolve=True
    )


async def quick_verify(
    macro_script: List[MacroStep],
    platform: str = "web"
) -> ModeRecommendation:
    """
    Quick single-round verification to check if macro is viable.

    Example:
        result = await quick_verify(my_macro)
        if result["recommended_mode"] != "agentic":
            # Safe to run deterministically
            pass
    """
    return await VerificationService.verify_and_select_mode(
        macro_script=macro_script,
        platform=platform
    )
