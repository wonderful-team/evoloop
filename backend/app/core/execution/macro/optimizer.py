import logging
from enum import Enum

from app.core.execution.macro.schema import (
    MacroActionType,
    MacroScript,
    MacroStep,
    MacroStepType,
)
from app.core.execution.macro.schemas import OptimizationResult

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    MERGE_WAITS = "merge_waits"
    REMOVE_DUPLICATES = "remove_duplicates"
    TIME_INTERVAL = "time_interval"
    FILTER_REDUNDANT = "filter_redundant"
    COALESCE_EXTRACTS = "coalesce_extracts"


class MacroOptimizer:
    """
    Standardized Macro Optimizer.
    Operates on MacroStep models to remove redundancy and optimize timing.
    """

    MIN_STEP_INTERVAL_MS = 300
    MIN_WAIT_DURATION_MS = 100
    MAX_WAIT_DURATION_MS = 5000
    DUPLICATE_DETECTION_WINDOW = 3
    REDUNDANT_ACTIONS = {MacroActionType.WAIT}
    LOW_VALUE_ACTIONS = {"mouse_move", "cursor_move", "hover"}

    def __init__(self, min_interval_ms: int = None, enable_all_strategies: bool = True):
        self.min_interval_ms = min_interval_ms or self.MIN_STEP_INTERVAL_MS
        self.strategies_enabled = {
            OptimizationStrategy.MERGE_WAITS: True,
            OptimizationStrategy.REMOVE_DUPLICATES: True,
            OptimizationStrategy.TIME_INTERVAL: True,
            OptimizationStrategy.FILTER_REDUNDANT: True,
            OptimizationStrategy.COALESCE_EXTRACTS: enable_all_strategies,
        }

    def optimize(self, script: MacroScript) -> tuple[MacroScript, OptimizationResult]:
        steps = script.steps
        if not steps:
            return script, OptimizationResult(0, 0, 0, 0, 0)

        original_count = len(steps)
        stats = {'removed': 0, 'merged': 0, 'time_saved': 0, 'strategies': []}

        # Lossless port of the 5-round optimization pipeline

        # Round 1: Filter redundant
        current_steps = steps
        if self.strategies_enabled[OptimizationStrategy.FILTER_REDUNDANT]:
            current_steps = self._filter_redundant(current_steps)
            stats['removed'] += original_count - len(current_steps)
            if len(current_steps) < original_count:
                stats['strategies'].append('filter_redundant')

        # Round 2: Merge waits
        if self.strategies_enabled[OptimizationStrategy.MERGE_WAITS]:
            prev_len = len(current_steps)
            current_steps, merge_count, time_saved = self._merge_waits(current_steps)
            stats['merged'] += merge_count
            stats['time_saved'] += time_saved
            if merge_count > 0:
                stats['strategies'].append('merge_waits')

        # Round 3: Remove duplicates
        if self.strategies_enabled[OptimizationStrategy.REMOVE_DUPLICATES]:
            prev_len = len(current_steps)
            current_steps, dup_count = self._remove_duplicates(current_steps)
            stats['removed'] += dup_count
            if dup_count > 0:
                stats['strategies'].append('remove_duplicates')

        # Round 4: Time interval optimization (Auto-wait insertion)
        if self.strategies_enabled[OptimizationStrategy.TIME_INTERVAL]:
            current_steps, time_saved = self._optimize_intervals(current_steps)
            stats['time_saved'] += time_saved
            if time_saved > 0:
                stats['strategies'].append('time_interval')

        # Round 5: Batch Extract Coalescing (Simplified Model Port)
        if self.strategies_enabled[OptimizationStrategy.COALESCE_EXTRACTS]:
            current_steps, coalesce_count = self._coalesce_extracts(current_steps)
            if coalesce_count > 0:
                stats['strategies'].append('coalesce_extracts')

        # Renumber and return
        for i, step in enumerate(current_steps, 1):
            step.step_number = i

        optimized_script = script.model_copy(update={"steps": current_steps})
        result = OptimizationResult(
            original_steps=original_count,
            optimized_steps=len(current_steps),
            removed_steps=stats['removed'],
            merged_steps=stats['merged'],
            time_saved_ms=stats['time_saved'],
            strategies_applied=stats['strategies']
        )
        return optimized_script, result

    def _filter_redundant(self, steps: list[MacroStep]) -> list[MacroStep]:
        filtered = []
        for step in steps:
            if step.event_type in self.LOW_VALUE_ACTIONS: continue
            if step.event_type == MacroActionType.WAIT:
                payload = step.payload or {}
                duration_ms = payload.get('duration_ms', 0)
                seconds = payload.get('seconds', 0)
                if (duration_ms + seconds * 1000) <= 0: continue
            filtered.append(step)
        return filtered

    def _merge_waits(self, steps: list[MacroStep]) -> tuple[list[MacroStep], int, int]:
        merged = []
        merge_count = 0
        time_saved = 0
        i = 0
        while i < len(steps):
            step = steps[i]
            if step.event_type != MacroActionType.WAIT:
                merged.append(step)
                i += 1
                continue

            total_wait_ms = step.payload.get('duration_ms', 0) + (step.payload.get('seconds', 0) * 1000)
            consecutive = 1
            j = i + 1
            while j < len(steps) and steps[j].event_type == MacroActionType.WAIT:
                total_wait_ms += steps[j].payload.get('duration_ms', 0) + (steps[j].payload.get('seconds', 0) * 1000)
                consecutive += 1
                j += 1

            new_step = step.model_copy()
            final_wait_ms = min(max(total_wait_ms, self.MIN_WAIT_DURATION_MS), self.MAX_WAIT_DURATION_MS)
            time_saved += (total_wait_ms - final_wait_ms) + (consecutive - 1) * 50
            new_step.payload['duration_ms'] = final_wait_ms
            if 'seconds' in new_step.payload:
                del new_step.payload['seconds'] # Standardize to duration_ms
            merged.append(new_step)
            merge_count += consecutive - 1
            i = j
        return merged, merge_count, time_saved

    def _remove_duplicates(self, steps: list[MacroStep]) -> tuple[list[MacroStep], int]:
        deduped = []
        removed = 0
        for i, step in enumerate(steps):
            if step.type != MacroStepType.ACTION:
                deduped.append(step)
                continue

            is_dup = False
            for prev in deduped[-self.DUPLICATE_DETECTION_WINDOW:]:
                if prev.event_type == step.event_type and prev.target_selector == step.target_selector:
                    # Fuzzy match coordinates for mobile/desktop
                    if step.event_type in (MacroActionType.CLICK, MacroActionType.TAP):
                        c_p, p_p = step.payload, prev.payload
                        if abs(c_p.get('x',0)-p_p.get('x',0)) < 0.01 and abs(c_p.get('y',0)-p_p.get('y',0)) < 0.01:
                            is_dup = True; break
                    elif step.event_type in (MacroActionType.INPUT, MacroActionType.TYPE_TEXT):
                        if step.payload.get('text') == prev.payload.get('text'):
                            is_dup = True; break
                    else:
                        # General payload match
                        if {k:v for k,v in step.payload.items() if k!='timestamp'} == {k:v for k,v in prev.payload.items() if k!='timestamp'}:
                            is_dup = True; break

            if is_dup:
                removed += 1
            else:
                deduped.append(step)
        return deduped, removed

    def _optimize_intervals(self, steps: list[MacroStep]) -> tuple[list[MacroStep], int]:
        optimized = []
        time_saved = 0
        last_ts = 0
        for step in steps:
            # We assume payload might have timestamp from trace
            ts = step.payload.get('timestamp', 0)
            if ts > 0 and last_ts > 0:
                interval = ts - last_ts
                if interval < self.min_interval_ms:
                    needed = self.min_interval_ms - interval
                    if optimized and optimized[-1].event_type == MacroActionType.WAIT:
                        optimized[-1].payload['duration_ms'] += needed
                    else:
                        wait_step = MacroStep(
                            step_number=0, type=MacroStepType.ACTION, event_type=MacroActionType.WAIT,
                            source=step.source, payload={'duration_ms': needed}, description="Auto-timing"
                        )
                        optimized.append(wait_step)
                    time_saved -= needed
            optimized.append(step)
            last_ts = ts if ts > 0 else last_ts
        return optimized, time_saved

    def _coalesce_extracts(self, steps: list[MacroStep]) -> tuple[list[MacroStep], int]:
        coalesced = []
        count = 0
        i = 0
        while i < len(steps):
            if steps[i].type != MacroStepType.EXTRACT:
                coalesced.append(steps[i])
                i += 1
                continue

            extracts = [steps[i]]
            j = i + 1
            while j < len(steps) and steps[j].type == MacroStepType.EXTRACT:
                extracts.append(steps[j])
                j += 1

            if len(extracts) == 1:
                coalesced.append(steps[i])
            else:
                batch = MacroStep(
                    step_number=steps[i].step_number, type=MacroStepType.EXTRACT,
                    extract_type="batch", source=steps[i].source,
                    payload={"batch": True, "count": len(extracts), "keys": [e.key for e in extracts]}
                )
                coalesced.append(batch)
                count += len(extracts) - 1
            i = j
        return coalesced, count
