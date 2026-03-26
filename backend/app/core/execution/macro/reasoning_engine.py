"""
AgentReasoningEngine - Phase 4: Perception-First Reasoning
Encapsulates LLM-based decision making for the verification loop.
"""

import logging
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from app.core.execution.macro.verification_models import AnomalyType, RedundancyCheckResult, RedundancyType, AIAnalysisResult, RoundReport, VerificationIssue
from app.infrastructure.llm.vision import VisionLLMFactory
from langchain_core.messages import HumanMessage, SystemMessage
from app.utils import render_template
from app.utils.yaml import safe_yaml_dumps

logger = logging.getLogger(__name__)


class ActionDecision(BaseModel):
    """Decision made by the reasoning engine"""
    action: str  # 'execute', 'correct', 'skip', 'retry', 'abort'
    reasoning: str
    suggested_step: Optional[Dict[str, Any]] = None
    additional_steps: List[Dict[str, Any]] = []
    confidence: float


class AgentReasoningEngine:
    """
    Reasoning Engine for Proactive Verification.
    Uses Vision LLM to understand the current UI state and decide on execution strategy.
    """

    def __init__(self, mental_model: str):
        self.mental_model = mental_model
        self.llm = VisionLLMFactory.create_vision_llm(temperature=0.1)

    def _render_template(self, template_name: str, **kwargs) -> str:
        """Render a Jinja2 template with the given context."""
        return render_template(template_name, **kwargs)

    async def decide_next_step(
        self,
        current_step: Dict[str, Any],
        ui_state: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
        is_recovery: bool = False,
        failure_reason: str = ""
    ) -> ActionDecision:
        """
        Decide the next action based on visual state and current macro step.

        Args:
            current_step: The macro step to execute
            ui_state: Current UI state (with screenshot)
            history: Execution history
            is_recovery: If True, this is a recovery attempt after failure
            failure_reason: Reason for previous failure (if is_recovery=True)
        """
        history = history or []
        screenshot_path = ui_state.get("screenshot")
        step_number = current_step.get("step_number", "?")
        context = "RECOVERY" if is_recovery else "DECISION"

        if not screenshot_path:
            logger.warning(f"[LLM:{context}:{step_number}] No screenshot available, falling back to direct execution")
            return ActionDecision(
                action="execute",
                reasoning="No screenshot available for visual reasoning, falling back to direct execution.",
                confidence=0.5
            )

        prompt = self._build_reasoning_prompt(current_step, ui_state, history, is_recovery, failure_reason)

        # Log the request
        logger.info(f"[LLM:{context}:{step_number}] Sending request to Vision LLM")
        logger.info(f"[LLM:{context}:{step_number}] Prompt:\n{prompt}")

        try:
            image_message = VisionLLMFactory.create_image_message(
                image_path=screenshot_path,
                prompt=prompt
            )

            response = await self.llm.ainvoke([image_message])
            content = response.content

            # Log the response
            logger.info(f"[LLM:{context}:{step_number}] Raw response received")
            logger.info(f"[LLM:{context}:{step_number}] Response content:\n{content}")

            # Ensure content is string for parsing
            content_str = str(content)
            if isinstance(content, list):
                content_str = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
            
            result = self._parse_reasoning_response(content_str, current_step)

            # Log parsed result
            logger.info(f"[LLM:{context}:{step_number}] Parsed decision: action={result.action}, confidence={result.confidence}")
            if result.additional_steps:
                logger.info(f"[LLM:{context}:{step_number}] Additional steps: {len(result.additional_steps)}")
            logger.info(f"[LLM:{context}:{step_number}] Reasoning: {result.reasoning}")

            return result

        except Exception as e:
            logger.error(f"[LLM:{context}:{step_number}] Decision failed: {e}")
            return ActionDecision(
                action="execute",
                reasoning=f"Reasoning error: {e}. Falling back to default execution.",
                confidence=0.0
            )

    async def verify_outcome(
        self,
        step: Dict[str, Any],
        pre_state: Dict[str, Any],
        post_state: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Verify if the action had the intended effect visually.
        Returns: (is_successful, reasoning)
        """
        post_screenshot = post_state.get("screenshot")
        step_number = step.get("step_number", "?")

        if not post_screenshot:
            logger.info(f"[LLM:VERIFY:{step_number}] No post-execution screenshot, skipping visual verification")
            return True, "No post-execution screenshot for visual verification."

        # Convert step to YAML for better readability
        step_yaml = safe_yaml_dumps([step]) if isinstance(step, dict) else safe_yaml_dumps(step)
        
        prompt = self._render_template(
            "macro/verify_outcome.prompt.j2",
            step_yaml=step_yaml
        )
        
        logger.info(f"[LLM:VERIFY:{step_number}] Sending verification request")
        logger.info(f"[LLM:VERIFY:{step_number}] Prompt:\n{prompt}")

        try:
            image_message = VisionLLMFactory.create_image_message(
                image_path=post_screenshot,
                prompt=prompt
            )

            response = await self.llm.ainvoke([image_message])
            content = response.content
            logger.info(f"[LLM:VERIFY:{step_number}] Response:\n{content}")

            # Ensure content is string for regex
            if isinstance(content, list):
                content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])

            json_match = re.search(r'\{.*\}', str(content), re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                success = data.get("success", True)
                reasoning = data.get("reasoning", "No details")
            else:
                success = True
                reasoning = "Could not parse JSON response, assuming success"

            logger.info(f"[LLM:VERIFY:{step_number}] Verification result: success={success},  Reasoning: {reasoning}")

            return success, reasoning

        except Exception as e:
            logger.error(f"[LLM:VERIFY:{step_number}] Verification failed: {e}")
            return False, f"Verification error: {e}"

    async def is_failure_terminal(
        self,
        step: Dict[str, Any],
        error: str
    ) -> bool:
        """
        Reason whether a failure at a specific step is terminal for the entire macro.
        Avoids hardcoded 'critical' types.
        """
        step_number = step.get("step_number", "?")
        # Convert step to YAML for better readability
        step_yaml = safe_yaml_dumps([step]) if isinstance(step, dict) else safe_yaml_dumps(step)
        
        prompt = self._render_template(
            "macro/is_failure_terminal.prompt.j2",
            step_yaml=step_yaml,
            error=error
        )
        logger.info(f"[LLM:TERMINAL:{step_number}] Checking if failure is terminal")
        logger.info(f"[LLM:TERMINAL:{step_number}] Error: {error}")
        logger.info(f"[LLM:TERMINAL:{step_number}] Prompt:\n{prompt}")

        try:
            response = await self.llm.ainvoke([SystemMessage(content=prompt)])
            content = response.content
            logger.info(f"[LLM:TERMINAL:{step_number}] Response:\n{content}")

            # Ensure content is string for regex
            if isinstance(content, list):
                content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])

            json_match = re.search(r'\{.*\}', str(content), re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                is_terminal = data.get("is_terminal", True)
                reasoning = data.get("reasoning", "No reasoning")
            else:
                is_terminal = True
                reasoning = "Parsing failed"

            logger.info(f"[LLM:TERMINAL:{step_number}] is_terminal={is_terminal}")
            logger.info(f"[LLM:TERMINAL:{step_number}] Reasoning: {reasoning}")

            return is_terminal
        except Exception as e:
            logger.warning(f"[LLM:TERMINAL:{step_number}] Analysis failed: {e}. Defaulting to terminal for safety.")
            return True

    def _build_reasoning_prompt(
        self,
        step: Dict[str, Any],
        ui_state: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
        is_recovery: bool = False,
        failure_reason: str = ""
    ) -> str:
        """Build the prompt for the Vision LLM"""

        # Build history context
        history = history or []
        history_context = history[-3:] if history else []

        # Convert step to YAML for better readability
        step_yaml = safe_yaml_dumps([step]) if isinstance(step, dict) else safe_yaml_dumps(step)

        return self._render_template(
            "macro/decide_next_step.prompt.j2",
            mental_model=self.mental_model,
            step_yaml=step_yaml,
            platform=ui_state.get('platform'),
            url_or_activity=ui_state.get('url') or ui_state.get('current_activity'),
            history_context=history_context,
            is_recovery=is_recovery,
            failure_reason=failure_reason
        )

    def _parse_reasoning_response(self, content: str, original_step: Dict[str, Any]) -> ActionDecision:
        """Parse LLM JSON response"""
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON found in response: {content[:200]}")

        data = json.loads(json_match.group())

        # Ensure suggested_step has step_number
        suggested = data.get("suggested_step")
        if suggested:
            # Inherit step_number from original if missing
            if "step_number" not in suggested:
                suggested["step_number"] = original_step.get("step_number")

            # Ensure required list fields exist to pass MacroScript validation
            # Handle both missing key AND None values
            for key in ["then_steps", "else_steps", "steps"]:
                if not suggested.get(key):  # Handles both missing key and None/empty
                    suggested[key] = original_step.get(key, [])

            # Ensure max_iterations exists for loop steps
            if not suggested.get("max_iterations"):  # Handles missing and None
                suggested["max_iterations"] = original_step.get("max_iterations", 50)

        # Also ensure additional_steps have required fields
        additional_steps = data.get("additional_steps", [])
        for add_step in additional_steps:
            for key in ["then_steps", "else_steps", "steps"]:
                if not add_step.get(key):  # Handles both missing key and None
                    add_step[key] = []
            if not add_step.get("max_iterations"):  # Handles missing and None
                add_step["max_iterations"] = 50

        return ActionDecision(
            action=data.get("action", "execute"),
            reasoning=data.get("reasoning", "No reasoning provided"),
            suggested_step=suggested,
            additional_steps=additional_steps,
            confidence=data.get("confidence", 0.5)
        )

    async def check_redundancy(
        self,
        step: Dict[str, Any],
        ui_state: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None
    ) -> RedundancyCheckResult:
        """
        Check if a step is redundant based on visual state and history.
        """
        history = history or []
        screenshot_path = ui_state.get("screenshot")
        step_number = step.get("step_number", "?")

        # Convert step to YAML for better readability
        step_yaml = safe_yaml_dumps([step]) if isinstance(step, dict) else safe_yaml_dumps(step)
        
        prompt = self._render_template(
            "macro/check_redundancy.prompt.j2",
            step_yaml=step_yaml
        )
        logger.info(f"[LLM:REDUNDANCY:{step_number}] Checking redundancy")

        try:
            if not screenshot_path:
                logger.info(f"[LLM:REDUNDANCY:{step_number}] No screenshot, skipping")
                return RedundancyCheckResult(is_redundant=False)

            logger.info(f"[LLM:REDUNDANCY:{step_number}] Prompt:\n{prompt}")

            image_message = VisionLLMFactory.create_image_message(
                image_path=screenshot_path,
                prompt=prompt
            )

            response = await self.llm.ainvoke([image_message])
            content = response.content
            logger.info(f"[LLM:REDUNDANCY:{step_number}] Response:\n{content}")

            # Ensure content is string for regex
            if isinstance(content, list):
                content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])

            json_match = re.search(r'\{.*\}', str(content), re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                result = RedundancyCheckResult(
                    is_redundant=data.get("is_redundant", False),
                    redundancy_type=RedundancyType(data.get("type", "none")),
                    reason=data.get("reason", "Agent reasoning"),
                    suggested_action=data.get("suggested_action", "keep")
                )
            else:
                result = RedundancyCheckResult(is_redundant=False)

            logger.info(f"[LLM:REDUNDANCY:{step_number}] Result: is_redundant={result.is_redundant}, type={result.redundancy_type.value}")
            return result

        except Exception as e:
            logger.warning(f"[LLM:REDUNDANCY:{step_number}] Check failed: {e}")
            return RedundancyCheckResult(is_redundant=False)

    async def analyze_results(
        self,
        reports: List[RoundReport],
        macro_script: List[Dict[str, Any]]
    ) -> AIAnalysisResult:
        """
        Analyze all verification rounds and generate a qualitative report.
        """
        # Prepare a condensed version of reports for LLM context
        condensed_reports = []
        for r in reports:
            condensed_reports.append({
                "round": r.round_number,
                "name": r.round_name,
                "stats": {
                    "total": r.total_steps,
                    "passed": r.passed_steps,
                    "failed": r.failed_steps,
                    "adapted": r.adapted_steps
                },
                "failures": [
                    {"step": s.step_number, "error": s.error_message}
                    for s in r.step_results if s.status == "failed"
                ]
            })

        prompt = self._render_template(
            "macro/analyze_results.prompt.j2",
            total_steps=len(macro_script),
            reports_json=json.dumps(condensed_reports, indent=2, ensure_ascii=False)
        )
        logger.info(f"[LLM:ANALYZE] Analyzing results from {len(reports)} rounds")
        logger.info(f"[LLM:ANALYZE] Prompt:\n{prompt}")

        try:
            response = await self.llm.ainvoke([SystemMessage(content=prompt)])
            content = response.content
            logger.info(f"[LLM:ANALYZE] Response:\n{content}")

            # Ensure content is string for regex
            if isinstance(content, list):
                content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])

            json_match = re.search(r'\{.*\}', str(content), re.DOTALL)
            if not json_match:
                return AIAnalysisResult(qualitative_assessment="Could not parse analysis JSON")

            data = json.loads(json_match.group())

            # Clean up issues data - filter None values from affected_steps
            raw_issues = data.get("issues", [])
            cleaned_issues = []
            for issue in raw_issues:
                if "affected_steps" in issue and issue["affected_steps"]:
                    # Filter out None/null values from affected_steps
                    issue["affected_steps"] = [
                        s for s in issue["affected_steps"] if s is not None
                    ]
                cleaned_issues.append(issue)

            result = AIAnalysisResult(
                issues=[VerificationIssue(**i) for i in cleaned_issues],
                recommendations=data.get("recommendations", []),
                recommended_execution_mode=data.get("recommended_execution_mode", "agentic"),
                confidence_score=data.get("confidence_score", 0.5),
                qualitative_assessment=data.get("qualitative_assessment", "Agent analysis complete.")
            )

            logger.info(f"[LLM:ANALYZE] Analysis complete: mode={result.recommended_execution_mode}, confidence={result.confidence_score}")
            logger.info(f"[LLM:ANALYZE] Found {len(result.issues)} issues, {len(result.recommendations)} recommendations")

            return result
        except Exception as e:
            logger.error(f"[LLM:ANALYZE] Analysis failed: {e}")
            return AIAnalysisResult(qualitative_assessment=f"Analysis failed: {e}")
