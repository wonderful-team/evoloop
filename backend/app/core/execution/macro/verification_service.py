"""
VerificationService - Phase 5: Integration Layer

High-level service for integrating agent-based verification with:
- MacroService (execution)
- SkillSynthesizer (learning)
- External API endpoints
"""

import logging
from typing import Any, Dict, List, Optional, Union

from app.core.execution.macro import (
    AgentMacroValidator,
    EnvironmentConfig,
    VerificationRequest,
    VerificationResponse,
    VerificationReporter,
)
from app.core.execution.macro.schema import MacroScript

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
        macro_script: Union[List[Dict[str, Any]], MacroScript],
        platform: str = "web",
        max_rounds: int = 2,
        auto_evolve: bool = True,
        thread_id: Optional[str] = None,
        stop_on_failure: bool = True
    ) -> Dict[str, Any]:
        """
        Verify a macro script with optional evolution.

        Args:
            macro_script: The macro script to verify
            platform: Target platform (web, android, desktop)
            max_rounds: Number of verification rounds
            auto_evolve: Whether to evolve the macro based on results
            thread_id: Optional thread ID for tracking
            stop_on_failure: If True, stop verification when a step fails.
                            If False, continue to next step after failure.

        Returns:
            Dictionary with verification results and evolved macro
        """
        # Convert MacroScript to list if needed
        if isinstance(macro_script, MacroScript):
            steps = [step.dict() for step in macro_script.steps]
        else:
            steps = macro_script

        if not steps:
            return {
                "success": False,
                "error": "Empty macro script",
                "evolved_macro": None,
                "execution_mode": "agentic"
            }

        # Build verification request with agent config
        from app.core.execution.macro.verification_models import AgentConfig
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
            result = {
                "success": response.success,
                "status": response.status.value,
                "execution_mode": response.execution_mode.value,
                "confidence_score": response.confidence_score,
                "rounds_completed": response.rounds_completed,
                "evolved_macro": response.evolved_macro if auto_evolve else None,
                "verification_report": {
                    "summary": {
                        "success_rate": response.verification_report.summary.overall_success_rate,
                        "adaptation_rate": response.verification_report.summary.adaptation_rate,
                        "anomalies_detected": response.verification_report.summary.total_anomalies_detected,
                        "adaptations_applied": response.verification_report.summary.total_adaptations_applied,
                    },
                    "issues": [
                        {
                            "severity": issue.severity,
                            "category": issue.category,
                            "description": issue.description,
                            "affected_steps": issue.affected_steps
                        }
                        for issue in response.verification_report.issues
                    ],
                    "recommendations": response.verification_report.recommendations
                },
                "markdown_report": reporter.to_markdown(),
            }

            logger.info(
                f"[VerificationService] Verification complete: "
                f"success={response.success}, mode={response.execution_mode.value}, "
                f"confidence={response.confidence_score:.2%}"
            )

            return result

        except Exception as e:
            logger.error(f"[VerificationService] Verification failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "evolved_macro": None,
                "execution_mode": "agentic"
            }

    @classmethod
    async def verify_and_select_mode(
        cls,
        macro_script: Union[List[Dict[str, Any]], MacroScript],
        platform: str = "web",
        confidence_threshold: float = 0.8
    ) -> Dict[str, Any]:
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
            return {
                "can_execute": False,
                "recommended_mode": "agentic",
                "reason": result.get("error", "Verification failed"),
                "confidence": 0.0
            }

        confidence = result["confidence_score"]

        if confidence >= confidence_threshold and result["status"] == "completed":
            return {
                "can_execute": True,
                "recommended_mode": "deterministic",
                "reason": f"High confidence ({confidence:.2%}) with no failures",
                "confidence": confidence
            }
        elif confidence >= 0.5:
            return {
                "can_execute": True,
                "recommended_mode": "hybrid",
                "reason": f"Moderate confidence ({confidence:.2%}), some adaptations needed",
                "confidence": confidence
            }
        else:
            return {
                "can_execute": True,
                "recommended_mode": "agentic",
                "reason": f"Low confidence ({confidence:.2%}), agent supervision recommended",
                "confidence": confidence
            }

    @classmethod
    async def evolve_macro(
        cls,
        macro_script: Union[List[Dict[str, Any]], MacroScript],
        platform: str = "web",
        max_rounds: int = 2
    ) -> Dict[str, Any]:
        """
        Evolve a macro through verification and adaptation.

        Returns the evolved macro with enhanced error handling.

        Args:
            macro_script: Original macro script
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
            return {
                "success": False,
                "error": result.get("error", "Evolution failed"),
                "original_macro": macro_script,
                "evolved_macro": None,
                "improvements": []
            }

        # Calculate improvements
        original_count = len(macro_script) if isinstance(macro_script, list) else len(macro_script.steps)
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

        return {
            "success": True,
            "original_macro": macro_script,
            "evolved_macro": result["evolved_macro"],
            "execution_mode": result["execution_mode"],
            "confidence": result["confidence_score"],
            "improvements": improvements,
            "report": result["verification_report"]
        }


class SynthesisIntegration:
    """
    Integration layer for SkillSynthesizer.

    Replaces the old verify_macro method with the new agent-based verification.
    """

    @staticmethod
    async def verify_for_synthesis(
        macro_script: List[Dict[str, Any]],
        thread_id: str,
        project_id: int = 1
    ) -> Dict[str, Any]:
        """
        Verify macro during skill synthesis.

        This is the drop-in replacement for the old verify_macro method.

        Args:
            macro_script: Compiled macro from trace
            thread_id: Thread ID for context
            project_id: Project ID for environment

        Returns:
            Verification result compatible with old interface
        """
        logger.info(f"[{thread_id}] Phase 5: Running agent-based verification")

        # Detect platform from macro
        platform = SynthesisIntegration._detect_platform(macro_script)

        # Run verification with 2 rounds (baseline + stress test)
        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform=platform,
            max_rounds=2,
            auto_evolve=True,
            thread_id=thread_id
        )

        # Convert to old interface for backwards compatibility
        if result["success"] and result["evolved_macro"]:
            return {
                "status": "success",
                "evolved_macro": result["evolved_macro"],
                "execution_mode": result["execution_mode"],
                "confidence": result["confidence_score"],
                "report": result["verification_report"]
            }
        else:
            return {
                "status": "failed",
                "error": result.get("error", "Verification failed"),
                "report": result.get("verification_report", {})
            }

    @staticmethod
    def _detect_platform(macro_script: List[Dict[str, Any]]) -> str:
        """Detect platform from macro steps"""
        sources = set()
        for step in macro_script:
            source = step.get("source", "dom")
            sources.add(source)

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
    ) -> Dict[str, Any]:
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

        # Execute via MacroService
        from app.core.execution.macro.service import MacroService

        return await MacroService.run(thread_id, macro_script, params)


# Convenience functions for direct import

async def verify_macro(
    macro_script: List[Dict[str, Any]],
    platform: str = "web",
    max_rounds: int = 2
) -> Dict[str, Any]:
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
    macro_script: List[Dict[str, Any]],
    platform: str = "web"
) -> Dict[str, Any]:
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
