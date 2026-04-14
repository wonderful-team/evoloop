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

from pydantic import BaseModel, Field

from app.core.execution.macro.verification_models import (
    AdaptationRecord,
    AnomalyType,
    MacroEvolutionRecord,
    StepExecutionStatus,
    StepResult,
)
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class EvolutionRule(DynamicBaseModel):
    """Rule for transforming a step based on anomaly type"""
    name: str
    anomaly_type: AnomalyType
    description: str
    priority: int = 0


class EvolutionContext(DynamicBaseModel):
    """Context for macro evolution"""
    original_macro: List[Dict[str, Any]]
    step_results: List[StepResult]
    evolution_records: List[MacroEvolutionRecord]
    target_platform: str = "web"

    # Track which steps have been modified
    modified_steps: Set[int] = Field(default_factory=set)

    # Track added steps (insertions)
    inserted_steps: Dict[int, List[Dict[str, Any]]] = Field(default_factory=dict)


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


class AgenticTransformer(StepTransformer):
    """
    General purpose transformer for Agent-derived evolution.
    
    Directly uses the evolved_step and additional_steps provided by the Agent
    in the MacroEvolutionRecord.
    """

    def can_transform(self, step: Dict[str, Any], record: MacroEvolutionRecord) -> bool:
        # This transformer handles any record that has an evolved step or additional steps
        return record.evolved_step is not None or (record.additional_steps and len(record.additional_steps) > 0)

    def transform(
        self,
        step: Dict[str, Any],
        record: MacroEvolutionRecord,
        context: EvolutionContext
    ) -> List[Dict[str, Any]]:
        """
        Transform: Use the Agent's decided output directly.
        """
        evolved_steps = []
        
        # 1. Add any additional steps the agent decided were necessary (e.g., recovery actions)
        if record.additional_steps:
            evolved_steps.extend(record.additional_steps)
            
        # 2. Use the evolved version of the original step
        if record.evolved_step:
            evolved_steps.append(record.evolved_step)
        else:
            # Fallback to original if no evolved version provided
            evolved_steps.append(copy.deepcopy(step))
            
        return evolved_steps

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
            AgenticTransformer(),
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
            # Use original step_number if present, otherwise fallback to sequential
            logical_step_number = step.get("step_number", idx + 1)

            # Skip redundant steps
            is_redundant = any(
                res.step_number == logical_step_number and res.status == StepExecutionStatus.REDUNDANT
                for res in step_results
            )
            if is_redundant:
                logger.info(f"[EvolutionEngine] Removing redundant step {logical_step_number}")
                step_offset -= 1
                continue

            # Update step number for re-sequencing (preserving global offset)
            step_number = logical_step_number # For internal use in this iteration
            step["step_number"] = step_number # Keep it consistent for evolution records lookup

            # Handle loop steps - process sub-steps recursively
            if step.get("type") == "loop":
                evolved_loop = self._evolve_loop_step(
                    step, step_number, evolution_records, context
                )
                evolved_loop["step_number"] = step_number + step_offset
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

                logger.info(
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
        """Apply appropriate transformers to a step

        When multiple records exist for the same step, transformations are merged
        cumulatively to preserve all corrections (e.g., coordinate fixes from
        COORDINATE_DRIFT should not be overwritten by STATE_MISMATCH records).

        Also handles additional_steps from adaptations (e.g., wait steps inserted
        before the main action to handle popups/obstructions).
        """
        evolved_steps = [copy.deepcopy(step)]
        step_number = step.get("step_number", 0)
        all_additional_steps: List[Dict[str, Any]] = []

        for record in records:
            # Collect additional steps from this record (e.g., wait for popup to clear)
            if record.additional_steps:
                all_additional_steps.extend(record.additional_steps)

            # Find applicable transformer
            transformed = False
            for transformer in self.transformers:
                if transformer.can_transform(step, record):
                    # Transform the first step in chain
                    # (transformers may expand 1 to many)
                    evolved_steps = transformer.transform(
                        evolved_steps[0], record, context
                    )
                    context.modified_steps.add(step_number)
                    transformed = True
                    break

            if not transformed:
                # No specific transformer for this record type
                # Merge evolved_step properties instead of replacing entirely
                if record.evolved_step:
                    merged_step = self._merge_step_evolution(
                        evolved_steps[0], record.evolved_step
                    )
                    evolved_steps = [merged_step]
                    context.modified_steps.add(step_number)

        # If there are additional steps (e.g., wait for obstruction to clear),
        # insert them before the evolved step
        if all_additional_steps:
            logger.info(f"[TransformStep] Step {step_number}: Inserting {len(all_additional_steps)} additional steps")
            # Return additional_steps first, then the evolved step(s)
            return all_additional_steps + evolved_steps

        return evolved_steps

    def _merge_step_evolution(
        self,
        current_step: Dict[str, Any],
        evolved_step: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge evolved_step properties into current_step.

        Preserves critical corrections like coordinate fixes while allowing
        other properties to be updated from the evolved_step.
        """
        merged = copy.deepcopy(current_step)

        # Merge payload fields - evolved_step takes precedence for most fields
        current_payload = merged.get("payload", {})
        evolved_payload = evolved_step.get("payload", {})

        # Fields that should NOT be overwritten (coordinate corrections)
        protected_fields = {"x", "y", "original_x", "original_y", "vision_corrected"}

        for key, value in evolved_payload.items():
            if key not in protected_fields:
                current_payload[key] = value

        # Update target_selector if provided in evolved_step
        if evolved_step.get("target_selector"):
            # Only update if current step doesn't have a vision-corrected coordinate
            current_payload = merged.get("payload", {})
            if not current_payload.get("vision_corrected"):
                merged["target_selector"] = evolved_step["target_selector"]

        merged["payload"] = current_payload

        # Log the merge
        step_num = current_step.get("step_number", "N/A")
        logger.info(f"[StepMerge] Step {step_num}: Merged evolution, protected fields: {protected_fields}")

        return merged

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
                logger.info(
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
        """Extract anomaly type from evolution record or reasoning"""
        # If the record has an anomaly_type set (from legacy logic), use it
        # Otherwise, the record from ReasoningEngine might not have a formal anomaly_type
        # mapping yet, so we just return 'agent_correction'
        return "agent_correction"

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
