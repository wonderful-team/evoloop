"""
AdaptationStrategyLibrary - Phase 2: Strategy Adaptation Library

Provides standard and LLM-powered adaptation strategies for each anomaly type.
Implements two-tier adaptation: quick fixes and deep LLM-based strategies.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.core.execution.macro.verification_models import (
    AnomalyType,
    AdaptationRecord,
)
from app.infrastructure.llm.factory import LLMFactory
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class AdaptationStrategy(ABC):
    """Abstract base class for adaptation strategies"""

    def __init__(self, anomaly_type: AnomalyType):
        self.anomaly_type = anomaly_type

    @abstractmethod
    async def adapt(
        self,
        step: Dict[str, Any],
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]],
        attempt_number: int = 1
    ) -> AdaptationRecord:
        """
        Generate adaptation for the given anomaly

        Returns:
            AdaptationRecord with adapted strategy and success status
        """
        pass

    def _create_record(
        self,
        original_step: Dict[str, Any],
        adapted_step: Dict[str, Any],
        reasoning: str,
        success: bool,
        attempt_number: int
    ) -> AdaptationRecord:
        """Helper to create adaptation record"""
        return AdaptationRecord(
            anomaly_type=self.anomaly_type,
            original_strategy=original_step,
            adapted_strategy=adapted_step,
            reasoning=reasoning,
            success=success,
            attempt_number=attempt_number
        )


class QuickFixStrategy(AdaptationStrategy):
    """
    Tier 1: Quick fix strategies using heuristics and rules
    No LLM call required - fast and deterministic
    """

    async def adapt(
        self,
        step: Dict[str, Any],
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]],
        attempt_number: int = 1
    ) -> AdaptationRecord:
        """Apply quick fix based on anomaly type

        Returns:
            AdaptationRecord with additional_steps field populated if extra steps needed
            (e.g., wait for popup to clear before main action)
        """
        handler = self._get_handler()
        if handler:
            try:
                result = await handler(step, anomaly_details, ui_state)

                # Handle both old format (step, reasoning) and new format (step, reasoning, additional_steps)
                if len(result) == 2:
                    adapted_step, reasoning = result
                    additional_steps = []
                else:
                    adapted_step, reasoning, additional_steps = result

                # Only mark as successful if the step was actually modified or additional steps were added
                is_modified = self._is_step_modified(step, adapted_step) or len(additional_steps) > 0
                if not is_modified:
                    logger.debug(f"[QuickFix] Handler returned unmodified step for {self.anomaly_type}")

                record = self._create_record(
                    step, adapted_step, reasoning, is_modified, attempt_number
                )
                # Store additional steps in the record
                record.additional_steps = additional_steps
                return record
            except Exception as e:
                logger.warning(f"[QuickFix] Handler failed: {e}")
                # Fall through to return failure

        return self._create_record(
            step, step, f"No quick fix available for {self.anomaly_type}", False, attempt_number
        )

    def _is_step_modified(self, original: Dict[str, Any], adapted: Dict[str, Any]) -> bool:
        """Check if the adapted step is meaningfully different from the original"""
        import json
        # Compare by serializing to JSON (ignores key order differences)
        try:
            return json.dumps(original, sort_keys=True) != json.dumps(adapted, sort_keys=True)
        except (TypeError, ValueError):
            # Fallback to simple comparison if serialization fails
            return original != adapted

    def _get_handler(self) -> Optional[Callable]:
        """Get the appropriate handler for this anomaly type"""
        handlers = {
            AnomalyType.COORDINATE_DRIFT: self._fix_coordinate_drift,
            AnomalyType.ELEMENT_NOT_FOUND: self._fix_element_not_found,
            AnomalyType.ELEMENT_OBSCURED: self._fix_element_obscured,
            AnomalyType.LOADING_TIMEOUT: self._fix_loading_timeout,
            AnomalyType.STATE_MISMATCH: self._fix_state_mismatch,
        }
        return handlers.get(self.anomaly_type)

    async def _fix_coordinate_drift(
        self,
        step: Dict[str, Any],
        details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        """
        Fix coordinate drift by using actual detected position
        or switching to selector-based approach

        优化：支持 Vision LLM 提供的 correct_coords
        Returns: (adapted_step, reasoning, additional_steps)
        """
        adapted = step.copy()
        payload = adapted.get("payload", {}).copy()
        additional_steps: List[Dict[str, Any]] = []

        # ========== 优化：优先使用 Vision LLM 提供的正确坐标 ==========
        correct_coords = details.get("correct_coords")
        if correct_coords and "x" in correct_coords and "y" in correct_coords:
            recorded_x = payload.get("x", 0)
            recorded_y = payload.get("y", 0)
            payload["x"] = correct_coords["x"]
            payload["y"] = correct_coords["y"]
            # 保留原始坐标信息用于追踪
            payload["original_x"] = recorded_x
            payload["original_y"] = recorded_y
            payload["vision_corrected"] = True
            adapted["payload"] = payload
            drift_distance = details.get("drift_distance", 0.0)
            return adapted, f"Vision LLM corrected coordinates: ({recorded_x:.3f}, {recorded_y:.3f}) -> ({correct_coords['x']:.3f}, {correct_coords['y']:.3f}), distance={drift_distance:.3f}", additional_steps

        # 原有逻辑：使用启发式检测提供的 actual position
        actual_pos = details.get("actual")
        if actual_pos and "x" in actual_pos and "y" in actual_pos:
            payload["x"] = actual_pos["x"]
            payload["y"] = actual_pos["y"]
            adapted["payload"] = payload
            return adapted, f"Updated coordinates to actual position: ({actual_pos['x']}, {actual_pos['y']})", additional_steps

        # Try to find element by text and get its coordinates
        target_selector = step.get("target_selector")
        if target_selector and ui_state:
            elements = ui_state.get("elements", [])
            for elem in elements:
                if target_selector in str(elem.get("text", "")):
                    bounds = elem.get("bounds", {})
                    if "center_x" in bounds and "center_y" in bounds:
                        payload["x"] = bounds["center_x"]
                        payload["y"] = bounds["center_y"]
                        adapted["payload"] = payload
                        return adapted, f"Switched to element center coordinates from UI dump", additional_steps

        return adapted, "No specific coordinate fix applied", additional_steps

    async def _fix_element_not_found(
        self,
        step: Dict[str, Any],
        details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        """
        Fix element not found by trying alternative selectors
        or switching to coordinate-based approach

        优化：支持使用 Vision LLM 提供的最近元素坐标
        Returns: (adapted_step, reasoning, additional_steps)
        """
        adapted = step.copy()
        payload = adapted.get("payload", {}).copy()
        additional_steps: List[Dict[str, Any]] = []

        # ========== 优化：优先使用 Vision LLM 提供的最近元素坐标 ==========
        nearest_coords = details.get("nearest_element_coords")
        if nearest_coords and "x" in nearest_coords and "y" in nearest_coords:
            recorded_x = payload.get("x", 0)
            recorded_y = payload.get("y", 0)
            payload["x"] = nearest_coords["x"]
            payload["y"] = nearest_coords["y"]
            payload["original_x"] = recorded_x
            payload["original_y"] = recorded_y
            payload["vision_corrected"] = True
            adapted["payload"] = payload
            return adapted, f"Vision LLM relocated to nearest element: ({nearest_coords['x']:.3f}, {nearest_coords['y']:.3f})", additional_steps

        original_selector = details.get("selector", step.get("target_selector"))

        # Strategy 1: Try fuzzy text match
        if ui_state and original_selector:
            elements = ui_state.get("elements", [])

            # Look for partial text matches
            for elem in elements:
                elem_text = str(elem.get("text", ""))
                if original_selector in elem_text or elem_text in original_selector:
                    # Found partial match - use this element's selector
                    new_selector = self._build_selector_from_element(elem)
                    if new_selector:
                        payload["selector"] = new_selector
                        adapted["payload"] = payload
                        adapted["target_selector"] = new_selector
                        return adapted, f"Switched to fuzzy matched selector: {new_selector}", additional_steps

        return adapted, "Applied generic retry strategy", additional_steps

    async def _fix_element_obscured(
        self,
        step: Dict[str, Any],
        details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        """
        Fix element obscured by adding a wait step before the action.
        Returns: (adapted_step, reasoning, additional_steps)
        """
        adapted = step.copy()

        # Add a wait step before the action to allow UI to stabilize
        additional_steps = []
        wait_step = {
            "type": "action",
            "event_type": "wait",
            "source": step.get("source", "dom"),
            "payload": {"duration_ms": 1000, "reason": "wait_for_obstruction_clear"}
        }
        additional_steps.append(wait_step)

        return adapted, "Added wait step for obstruction to clear", additional_steps

    async def _fix_loading_timeout(
        self,
        step: Dict[str, Any],
        details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        """
        Fix loading timeout by increasing wait duration
        Engine-compatible: uses duration_ms (not timeout_ms)
        Returns: (adapted_step, reasoning, additional_steps)
        """
        adapted = step.copy()
        payload = adapted.get("payload", {}).copy()
        additional_steps: List[Dict[str, Any]] = []

        # Engine uses duration_ms for wait steps
        current_duration = payload.get("duration_ms", 5000)
        new_duration = min(current_duration * 2, 30000)  # Cap at 30s

        payload["duration_ms"] = new_duration
        adapted["payload"] = payload

        return adapted, f"Increased wait duration from {current_duration}ms to {new_duration}ms", additional_steps

    async def _fix_state_mismatch(
        self,
        step: Dict[str, Any],
        details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        """
        Fix state mismatch by adding verification step or correcting coordinates
        Returns: (adapted_step, reasoning, additional_steps)
        """
        adapted = step.copy()
        additional_steps: List[Dict[str, Any]] = []
        payload = adapted.get("payload", {}).copy()

        # Skip if already corrected by Vision LLM - avoid double correction
        if payload.get("vision_corrected"):
            return adapted, "Step already corrected by Vision LLM, skipping heuristic adjustment", additional_steps

        # Case 0: App launch failed (package name mismatch)
        expected_package = details.get("expected_package")
        actual_package = details.get("actual_package")
        if expected_package and actual_package:
            # Add delay and retry flag for app launch
            payload["retry_launch"] = True
            payload["force_stop"] = True  # Force stop before relaunch
            adapted["payload"] = payload
            return adapted, f"App launch failed: expected {expected_package}, got {actual_package}. Will retry with force_stop.", additional_steps

        # Check if Vision LLM detected wrong page and suggested fix
        vision_analysis = details.get("vision_analysis", False)
        suggested_fix = details.get("suggested_fix", "")
        no_state_change = details.get("no_state_change_detected", False)
        current_coords = details.get("current_coords")

        # Case 1: Vision LLM detected issue - but we skip since it should have been handled
        # by _fix_coordinate_drift which sets vision_corrected flag
        if vision_analysis and suggested_fix:
            # This case should rarely be reached now due to vision_corrected check above
            # Keep for backward compatibility
            current_coords = payload.get("x"), payload.get("y")

            if current_coords[0] is not None and current_coords[1] is not None:
                # Try offset correction (move down/right to find correct element)
                offset_x = 0.05  # 5% screen width offset
                offset_y = 0.08  # 8% screen height offset

                new_x = min(current_coords[0] + offset_x, 0.9)
                new_y = min(current_coords[1] + offset_y, 0.9)

                payload["x"] = new_x
                payload["y"] = new_y

                adapted["payload"] = payload
                return adapted, f"Corrected coordinates based on Vision LLM analysis: ({current_coords[0]:.3f}, {current_coords[1]:.3f}) -> ({new_x:.3f}, {new_y:.3f})", additional_steps

        # Case 2: No state change detected (click didn't work) - try coordinate correction
        if no_state_change and current_coords and suggested_fix:
            x, y = current_coords.get("x"), current_coords.get("y")
            if x is not None and y is not None:
                # Try offset correction
                offset_x = 0.05
                offset_y = 0.08

                new_x = min(x + offset_x, 0.9)
                new_y = min(y + offset_y, 0.9)

                payload["x"] = new_x
                payload["y"] = new_y

                adapted["payload"] = payload
                return adapted, f"Corrected coordinates (no state change detected): ({x:.3f}, {y:.3f}) -> ({new_x:.3f}, {new_y:.3f})", additional_steps

        return adapted, "Applied generic retry strategy", additional_steps

    def _build_selector_from_element(self, elem: Dict[str, Any]) -> Optional[str]:
        """Build a selector from element properties"""
        # Try resource-id first (most reliable on mobile)
        resource_id = elem.get("resource_id")
        if resource_id and resource_id != "null":
            return f"//*[@resource-id='{resource_id}']"

        # Try accessibility id
        content_desc = elem.get("content_desc")
        if content_desc:
            return f"//*[@content-desc='{content_desc}']"

        # Try text
        text = elem.get("text")
        if text:
            return f"//*[@text='{text}']"

        # Try class + index
        class_name = elem.get("class", "")
        index = elem.get("index", 0)
        if class_name:
            return f"//{class_name.split('.')[-1]}[{index}]"

        return None


class LLMDeepStrategy(AdaptationStrategy):
    """
    Tier 2: Deep adaptation using LLM reasoning
    Called when quick fixes fail or for complex scenarios
    """

    def __init__(self, anomaly_type: AnomalyType):
        super().__init__(anomaly_type)
        self.llm = None

    async def adapt(
        self,
        step: Dict[str, Any],
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]],
        attempt_number: int = 1
    ) -> AdaptationRecord:
        """Generate LLM-powered adaptation"""

        try:
            # Initialize LLM if needed
            if not self.llm:
                self.llm = LLMFactory.create_llm()

            # Build comprehensive prompt
            prompt = self._build_adaptation_prompt(step, anomaly_details, ui_state)

            # Call LLM
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content="Generate the adaptation strategy as JSON.")
            ]

            response = await self.llm.ainvoke(messages)
            content = response.content

            # Parse response
            adapted_step, reasoning = self._parse_llm_response(content, step)

            return self._create_record(
                step, adapted_step, reasoning, True, attempt_number
            )

        except Exception as e:
            logger.error(f"[LLMDeep] Adaptation failed: {e}")
            return self._create_record(
                step, step, f"LLM adaptation failed: {e}", False, attempt_number
            )

    def _build_adaptation_prompt(
        self,
        step: Dict[str, Any],
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]]
    ) -> str:
        """Build comprehensive prompt for LLM adaptation"""

        ui_context = ""
        if ui_state:
            elements = ui_state.get("elements", [])
            ui_context = f"""
Current UI State:
- Platform: {ui_state.get('platform', 'unknown')}
- Current Activity/URL: {ui_state.get('current_activity') or ui_state.get('url', 'unknown')}
- Available Elements (first 20):
"""
            for i, elem in enumerate(elements[:20], 1):
                text = elem.get('text', '')
                res_id = elem.get('resource_id', '')
                class_name = elem.get('class', '').split('.')[-1]
                if text or res_id:
                    ui_context += f"  {i}. {class_name}: text='{text[:50]}', id='{res_id}'\n"

        anomaly_specific_guidance = {
            AnomalyType.COORDINATE_DRIFT: """
Coordinate Drift Fix Options:
1. Use element selector instead of coordinates
2. Calculate relative position based on screen size
3. Use accessibility labels or text content
4. Apply offset correction based on detected drift
""",
            AnomalyType.ELEMENT_NOT_FOUND: """
Element Not Found Fix Options:
1. Try alternative selectors (id, text, class, xpath)
2. Wait longer for dynamic content to load
3. Scroll to make element visible
4. Use parent element + relative path
5. Check if element is in iframe/webview
""",
            AnomalyType.ELEMENT_OBSCURED: """
Element Obscured Fix Options:
1. Dismiss popup/dialog first (click outside, ESC key, close button)
2. Scroll element into view
3. Click through overlay if transparent
4. Wait for animation to complete
""",
            AnomalyType.LOADING_TIMEOUT: """
Loading Timeout Fix Options:
1. Increase wait duration significantly
2. Change wait condition (wait for specific element instead of time)
3. Check for loading indicators and wait for disappearance
4. Implement polling with shorter intervals
""",
            AnomalyType.STATE_MISMATCH: """
State Mismatch Fix Options:
1. Add explicit wait for expected state
2. Refresh/check current state before proceeding
3. Add intermediate verification steps
4. Handle conditional flows (if X then Y else Z)
""",
            AnomalyType.UNEXPECTED_FLOW: """
Unexpected Flow Fix Options:
1. Add conditional branch for this new state
2. Navigate back to expected path
3. Treat as valid alternative path and continue
4. Add checkpoint to verify current position
""",
        }.get(self.anomaly_type, "Analyze the situation and provide the best fix.")

        return f"""You are an expert UI automation engineer specializing in fixing broken automation scripts.

## Original Step
```json
{json.dumps(step, indent=2, ensure_ascii=False)}
```

## Detected Anomaly
- Type: {self.anomaly_type.value}
- Details: {json.dumps(anomaly_details, indent=2, ensure_ascii=False)}

{ui_context}

## Fix Guidelines
{anomaly_specific_guidance}

## Response Format
Return ONLY a JSON object in this exact format:

```json
{{
  "adapted_step": {{
    // The complete modified step
    // Must include all required fields
    // Can include additional fields for robustness
  }},
  "reasoning": "Detailed explanation of why this fix was chosen and how it addresses the anomaly",
  "confidence": 0.85,  // 0-1 confidence score
  "alternative_approaches": [
    "Brief description of alternative approaches considered"
  ]
}}
```

## Key Principles
1. Preserve the original intent of the step
2. Make the step more robust to environmental variations
3. Prefer selector-based approaches over coordinates
4. Add appropriate waits for dynamic content
5. Consider mobile vs desktop differences
6. The adapted_step must be a complete, valid step object

Generate the adaptation now:"""

    def _parse_llm_response(
        self,
        content: str,
        original_step: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        """Parse LLM response to extract adapted step"""

        # Extract JSON from markdown code blocks if present
        import re

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        try:
            data = json.loads(content)
            adapted_step = data.get("adapted_step", original_step)
            reasoning = data.get("reasoning", "No reasoning provided")

            # Ensure step_number is preserved
            if "step_number" in original_step and "step_number" not in adapted_step:
                adapted_step["step_number"] = original_step["step_number"]

            return adapted_step, reasoning

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            # Try to extract step from text
            return original_step, f"Failed to parse response: {content[:200]}"


class AdaptationStrategyLibrary:
    """
    Central library for managing and executing adaptation strategies.

    Implements two-tier adaptation:
    1. Quick fixes: Fast heuristics-based adaptations
    2. Deep adaptations: LLM-powered intelligent fixes
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self.quick_strategies: Dict[AnomalyType, QuickFixStrategy] = {}
        self.llm_strategies: Dict[AnomalyType, LLMDeepStrategy] = {}
        self._init_strategies()

    def _init_strategies(self) -> None:
        """Initialize all strategy instances"""
        for anomaly_type in AnomalyType:
            self.quick_strategies[anomaly_type] = QuickFixStrategy(anomaly_type)
            if self.use_llm:
                self.llm_strategies[anomaly_type] = LLMDeepStrategy(anomaly_type)

    async def adapt(
        self,
        step: Dict[str, Any],
        anomaly_type: AnomalyType,
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]] = None,
        attempt_number: int = 1,
        prefer_llm: bool = False
    ) -> AdaptationRecord:
        """
        Execute adaptation strategy for the given anomaly

        Args:
            step: The original step that failed
            anomaly_type: Type of detected anomaly
            anomaly_details: Details about the anomaly
            ui_state: Current UI state for context
            attempt_number: Which adaptation attempt this is
            prefer_llm: Skip quick fix and go straight to LLM

        Returns:
            AdaptationRecord with results
        """
        logger.info(f"[AdaptationLibrary] Adapting for {anomaly_type.value} (attempt {attempt_number})")

        # Tier 1: Quick fix (unless LLM preferred)
        if not prefer_llm and anomaly_type in self.quick_strategies:
            quick_result = await self.quick_strategies[anomaly_type].adapt(
                step, anomaly_details, ui_state, attempt_number
            )

            if quick_result.success:
                logger.info(f"[AdaptationLibrary] Quick fix succeeded")
                return quick_result

            logger.info(f"[AdaptationLibrary] Quick fix failed, escalating to LLM")

        # Tier 2: LLM deep adaptation
        if self.use_llm and anomaly_type in self.llm_strategies:
            llm_result = await self.llm_strategies[anomaly_type].adapt(
                step, anomaly_details, ui_state, attempt_number
            )
            return llm_result

        # No strategy available
        return AdaptationRecord(
            anomaly_type=anomaly_type,
            original_strategy=step,
            adapted_strategy=step,
            reasoning=f"No adaptation strategy available for {anomaly_type}",
            success=False,
            attempt_number=attempt_number
        )

    async def adapt_with_fallback(
        self,
        step: Dict[str, Any],
        anomaly_type: AnomalyType,
        anomaly_details: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3
    ) -> List[AdaptationRecord]:
        """
        Try multiple adaptation strategies with fallback

        Returns:
            List of all adaptation attempts
        """
        records = []

        for attempt in range(1, max_attempts + 1):
            # First try quick fix
            if attempt == 1:
                record = await self.adapt(
                    step, anomaly_type, anomaly_details, ui_state, attempt, prefer_llm=False
                )
                records.append(record)

                if record.success:
                    break

                # Use adapted step as input for next attempt
                step = record.adapted_strategy

            # Then try LLM
            else:
                record = await self.adapt(
                    step, anomaly_type, anomaly_details, ui_state, attempt, prefer_llm=True
                )
                records.append(record)

                if record.success:
                    break

                step = record.adapted_strategy

        return records

    def get_strategy_description(self, anomaly_type: AnomalyType) -> str:
        """Get human-readable description of strategies for an anomaly type"""
        descriptions = {
            AnomalyType.COORDINATE_DRIFT: "Coordinate drift: Updates coordinates or switches to selector-based approach",
            AnomalyType.ELEMENT_NOT_FOUND: "Element not found: Tries alternative selectors or fallback to coordinates",
            AnomalyType.ELEMENT_OBSCURED: "Element obscured: Dismisses popups/dialogs blocking the target",
            AnomalyType.LOADING_TIMEOUT: "Loading timeout: Increases wait duration or changes wait condition",
            AnomalyType.STATE_MISMATCH: "State mismatch: Adds verification and stabilization waits",
            AnomalyType.UNEXPECTED_FLOW: "Unexpected flow: Adds conditional handling for alternative paths",
            AnomalyType.DATA_MISMATCH: "Data mismatch: Validates expected data format/content",
            AnomalyType.ENVIRONMENT_ERROR: "Environment error: Retries with environment stabilization",
        }
        return descriptions.get(anomaly_type, f"{anomaly_type.value}: Uses LLM-powered adaptation")
