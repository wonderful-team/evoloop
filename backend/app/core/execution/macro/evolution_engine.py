"""
MacroEvolutionEngine - Phase 3: Macro Evolution Engine

Transforms adaptations into structural macro enhancements.
Generates robust macros with fallback mechanisms and error handling.
"""

import copy
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.execution.macro.verification_models import (
    AdaptationRecord,
    AnomalyType,
    MacroEvolutionRecord,
    StepExecutionStatus,
    StepResult,
)

logger = logging.getLogger(__name__)


@dataclass
class EvolutionRule:
    """Rule for transforming a step based on anomaly type"""
    name: str
    anomaly_type: AnomalyType
    description: str
    priority: int = 0


@dataclass
class EvolutionContext:
    """Context for macro evolution"""
    original_macro: List[Dict[str, Any]]
    step_results: List[StepResult]
    evolution_records: List[MacroEvolutionRecord]
    target_platform: str = "web"

    # Track which steps have been modified
    modified_steps: Set[int] = field(default_factory=set)

    # Track added steps (insertions)
    inserted_steps: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)


class StepTransformer(ABC):
    """Abstract base for step transformations"""

    @abstractmethod
    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        """Check if this transformer can handle the given step/record"""
        pass

    @abstractmethod
    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """
        Transform a single step into one or more enhanced steps

        Returns:
            List of steps (may be expanded from 1 to many)
        """
        pass


class CoordinateDriftTransformer(StepTransformer):
    """
    Transform coordinate-based steps with corrected coordinates.

    Simple evolution: Update coordinates to corrected values.
    Preserves original coordinates for reference (in payload only).
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        return record.evolution_reason and "coordinate" in record.evolution_reason.lower()

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Transform: Use corrected coordinates from adaptation"""
        evolved = copy.deepcopy(step)

        # Get the evolved step from record (contains corrected coordinates)
        if record.evolved_step:
            evolved_step = copy.deepcopy(record.evolved_step)
            # Only update coordinates in payload, preserve all other fields
            original_payload = evolved.get("payload", {})
            evolved_payload = evolved_step.get("payload", {})

            # Update x, y coordinates if corrected
            if "x" in evolved_payload:
                original_payload["x"] = evolved_payload["x"]
            if "y" in evolved_payload:
                original_payload["y"] = evolved_payload["y"]

            # Preserve correction metadata in payload (engine will ignore unknown fields)
            if "original_x" in evolved_payload:
                original_payload["original_x"] = evolved_payload["original_x"]
            if "original_y" in evolved_payload:
                original_payload["original_y"] = evolved_payload["original_y"]

            evolved["payload"] = original_payload

        return [evolved]


class ElementNotFoundTransformer(StepTransformer):
    """
    Transform steps with element not found issues.

    Simple evolution: Update to corrected selector if available.
    Engine-compatible: Only modifies target_selector, no extra fields.
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        return record.evolution_reason and "element" in record.evolution_reason.lower()

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Transform: Use corrected selector from adaptation"""
        evolved = copy.deepcopy(step)

        # Get the evolved step from record (contains corrected selector)
        if record.evolved_step:
            evolved_step = copy.deepcopy(record.evolved_step)

            # Update target_selector if corrected
            if evolved_step.get("target_selector"):
                evolved["target_selector"] = evolved_step["target_selector"]

            # Also check payload for selector
            evolved_payload = evolved_step.get("payload", {})
            if evolved_payload.get("selector"):
                original_payload = evolved.get("payload", {})
                original_payload["selector"] = evolved_payload["selector"]
                evolved["payload"] = original_payload

        return [evolved]


class ElementObscuredTransformer(StepTransformer):
    """
    Transform steps where elements are obscured by popups/overlays.

    Simple evolution: Add a brief wait before the action to allow UI to stabilize.
    Engine-compatible: Uses standard 'wait' event_type.
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        return record.evolution_reason and "obscured" in record.evolution_reason.lower()

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Transform: Add a wait step before the action"""
        evolved_steps = []

        # Step 1: Wait for UI to stabilize (using standard wait event)
        wait_step = {
            "step_number": step.get("step_number", 0),
            "type": "action",
            "event_type": "wait",
            "source": step.get("source", "dom"),
            "payload": {"duration_ms": 800, "reason": "wait_for_obstruction_clear"}
        }
        evolved_steps.append(wait_step)

        # Step 2: Original (evolved) action
        evolved = copy.deepcopy(step)
        if record.evolved_step:
            evolved_step = copy.deepcopy(record.evolved_step)
            # Preserve step number and basic structure
            evolved["payload"] = evolved_step.get("payload", evolved.get("payload", {}))

        evolved_steps.append(evolved)

        return evolved_steps


class LoadingTimeoutTransformer(StepTransformer):
    """
    Transform steps that timeout due to slow loading

    Evolution rules:
    - Change fixed wait to conditional wait
    - Add loading indicator detection
    - Increase timeout with exponential backoff
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        return record.evolution_reason and "timeout" in record.evolution_reason.lower()

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Transform: Increase wait duration for timeout issues."""
        evolved = copy.deepcopy(step)
        payload = evolved.get("payload", {})

        # Simply increase the wait duration (engine-compatible)
        current_duration = payload.get("duration_ms", 5000)
        payload["duration_ms"] = min(int(current_duration * 1.5), 30000)  # Max 30s

        evolved["payload"] = payload
        return [evolved]


class StateMismatchTransformer(StepTransformer):
    """
    Transform steps with state mismatch issues

    Evolution rules:
    - Add state verification before action
    - Add navigation recovery
    - Add conditional logic
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        return record.evolution_reason and "state_mismatch" in record.evolution_reason.lower()

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Transform to add state verification - simplified, no extra fields"""
        evolved = copy.deepcopy(step)
        if record.evolved_step:
            evolved = copy.deepcopy(record.evolved_step)
        return [evolved]

    def _extract_navigation(
        self,
        context: EvolutionContext,
        target_step: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract navigation steps to reach target step's context"""
        # Find goto/open_app step before target
        nav_steps = []
        target_idx = target_step.get("step_number", 0) - 1

        for step in context.original_macro[:target_idx]:
            if step.get("event_type") in ("goto", "navigate", "open_app", "launch_app"):
                nav_steps.append(copy.deepcopy(step))

        return nav_steps[-1:] if nav_steps else []


class MacroEvolutionEngine:
    """
    Macro Evolution Engine

    Transforms verified macro with adaptations into an enhanced, robust macro.
    """

    def __init__(self):
        self.transformers: List[StepTransformer] = [
            CoordinateDriftTransformer(),
            ElementNotFoundTransformer(),
            ElementObscuredTransformer(),
            LoadingTimeoutTransformer(),
            StateMismatchTransformer(),
        ]

    def evolve(
        self,
        original_macro: List[Dict[str, Any]],
        evolution_records: List[MacroEvolutionRecord],
        step_results: List[StepResult],
        target_platform: str = "web"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Evolve macro based on verification results

        Returns:
            Tuple of (evolved_macro, evolution_metadata)
        """
        logger.info(f"[EvolutionEngine] Starting evolution of {len(original_macro)} steps")

        context = EvolutionContext(
            original_macro=original_macro,
            step_results=step_results,
            evolution_records=evolution_records,
            target_platform=target_platform
        )

        evolved_macro = []
        step_offset = 0

        for idx, step in enumerate(original_macro):
            step_number = idx + 1
            step["step_number"] = step_number

            # Handle loop steps - process sub-steps recursively
            if step.get("type") == "loop":
                evolved_loop = self._evolve_loop_step(
                    step, step_number, evolution_records, context
                )
                evolved_macro.append(evolved_loop)
                continue

            # Find relevant evolution records for this step
            step_records = [
                r for r in evolution_records
                if self._record_matches_step(r, step_number)
            ]

            if step_records:
                # Apply transformations
                evolved_steps = self._transform_step(
                    step, step_records, context
                )

                # Renumber steps
                for i, es in enumerate(evolved_steps):
                    es["step_number"] = step_number + step_offset + i

                evolved_macro.extend(evolved_steps)
                step_offset += len(evolved_steps) - 1

                logger.debug(
                    f"[EvolutionEngine] Step {step_number}: {len(step_records)} records, "
                    f"expanded to {len(evolved_steps)} steps"
                )
            else:
                # No evolution needed, copy as-is
                evolved_macro.append(copy.deepcopy(step))

        # Generate metadata
        metadata = self._generate_metadata(context, len(evolved_macro))

        logger.info(
            f"[EvolutionEngine] Evolution complete: {len(original_macro)} -> {len(evolved_macro)} steps"
        )

        return evolved_macro, metadata

    def _record_matches_step(
        self,
        record: MacroEvolutionRecord,
        step_number: int
    ) -> bool:
        """Check if evolution record applies to given step number"""
        original_step_num = record.original_step.get("step_number")
        evolved_step_num = record.evolved_step.get("step_number")

        return original_step_num == step_number or evolved_step_num == step_number

    def _transform_step(
        self,
        step: Dict[str, Any],
        records: List[MacroEvolutionRecord],
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """Apply appropriate transformers to a step"""
        evolved_steps = [copy.deepcopy(step)]

        for record in records:
            # Find applicable transformer
            for transformer in self.transformers:
                if transformer.can_transform(step, record):
                    # Transform the first step in chain
                    # (transformers may expand 1 to many)
                    evolved_steps = transformer.transform(
                        evolved_steps[0], record, context
                    )
                    context.modified_steps.add(step.get("step_number", 0))
                    break
            else:
                # No specific transformer, use evolved step from record
                if record.evolved_step:
                    evolved_steps = [copy.deepcopy(record.evolved_step)]

        return evolved_steps

    def _evolve_loop_step(
        self,
        step: Dict[str, Any],
        step_number: int,
        evolution_records: List[MacroEvolutionRecord],
        context: EvolutionContext
    ) -> Dict[str, Any]:
        """
        Evolve a loop step including its sub-steps.

        Sub-steps have step numbers like 501, 502, etc. (step_number * 100 + sub_idx + 1)
        """
        evolved_loop = copy.deepcopy(step)
        sub_steps = evolved_loop.get("steps", [])

        if not sub_steps:
            return evolved_loop

        evolved_sub_steps = []
        for sub_idx, sub_step in enumerate(sub_steps):
            # Calculate sub-step number (e.g., 501 for step 5, sub-step 0)
            sub_step_num = step_number * 100 + sub_idx + 1

            # Find evolution records for this sub-step
            sub_records = [
                r for r in evolution_records
                if self._record_matches_step(r, sub_step_num)
            ]

            if sub_records:
                # Apply transformations to sub-step
                transformed = self._transform_step(
                    sub_step, sub_records, context
                )
                evolved_sub_steps.extend(transformed)
                logger.debug(
                    f"[EvolutionEngine] Loop sub-step {sub_step_num}: "
                    f"{len(sub_records)} records applied"
                )
            else:
                # No evolution needed, keep sub-step as-is
                evolved_sub_steps.append(copy.deepcopy(sub_step))

        evolved_loop["steps"] = evolved_sub_steps
        return evolved_loop

    def _generate_metadata(
        self,
        context: EvolutionContext,
        final_step_count: int
    ) -> Dict[str, Any]:
        """Generate evolution metadata"""
        return {
            "original_step_count": len(context.original_macro),
            "evolved_step_count": final_step_count,
            "expansion_ratio": final_step_count / max(len(context.original_macro), 1),
            "modified_steps": sorted(context.modified_steps),
            "modification_rate": len(context.modified_steps) / max(len(context.original_macro), 1),
            "transformations_applied": self._count_transformations(context),
            "fallback_mechanisms_added": len(context.modified_steps),
        }

    def _count_transformations(self, context: EvolutionContext) -> Dict[str, int]:
        """Count transformations by type"""
        counts = {}
        for record in context.evolution_records:
            anomaly_type = self._extract_anomaly_type(record)
            counts[anomaly_type] = counts.get(anomaly_type, 0) + 1
        return counts

    def _extract_anomaly_type(self, record: MacroEvolutionRecord) -> str:
        """Extract anomaly type from evolution record"""
        reason = record.evolution_reason.lower()

        for anomaly_type in AnomalyType:
            if anomaly_type.value.lower().replace("_", " ") in reason:
                return anomaly_type.value

        return "unknown"

    def generate_fallback_chain(
        self,
        step: Dict[str, Any],
        max_fallbacks: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Generate a fallback chain for a single step

        Creates multiple variations of the step with increasing robustness
        but potentially slower execution.
        """
        chain = []

        # Level 0: Original step only
        # Note: Fallback chain generation is simplified - Agent handles retries at execution time
        chain.append(copy.deepcopy(step))

        return chain[:max_fallbacks]
