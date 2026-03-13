"""
Unit tests for MacroEvolutionEngine (Phase 3)
"""

import pytest

from app.core.execution.macro import (
    MacroEvolutionEngine,
    EvolutionOptimizer,
    CoordinateDriftTransformer,
    ElementNotFoundTransformer,
    ElementObscuredTransformer,
    LoadingTimeoutTransformer,
    StateMismatchTransformer,
    EvolutionContext,
    MacroEvolutionRecord,
    AnomalyType,
)


class TestMacroEvolutionEngine:
    """Test macro evolution engine"""

    @pytest.fixture
    def sample_macro(self):
        return [
            {"step_number": 1, "type": "action", "event_type": "goto", "payload": {}},
            {"step_number": 2, "type": "action", "event_type": "click", "payload": {"x": 100, "y": 200}},
        ]

    @pytest.fixture
    def sample_evolution_records(self):
        return [
            MacroEvolutionRecord(
                original_step={"step_number": 2, "type": "action"},
                evolved_step={"step_number": 2, "type": "action", "modified": True},
                evolution_reason="Phase 2: coordinate_drift - Fixed coordinates",
                confidence=0.85
            )
        ]

    def test_basic_evolution(self, sample_macro, sample_evolution_records):
        """Test basic macro evolution"""
        engine = MacroEvolutionEngine()

        evolved_macro, metadata = engine.evolve(
            original_macro=sample_macro,
            evolution_records=sample_evolution_records,
            step_results=[],
            target_platform="web"
        )

        assert len(evolved_macro) >= len(sample_macro)
        assert metadata["original_step_count"] == len(sample_macro)
        assert metadata["evolved_step_count"] == len(evolved_macro)

    def test_metadata_generation(self, sample_macro, sample_evolution_records):
        """Test evolution metadata generation"""
        engine = MacroEvolutionEngine()

        _, metadata = engine.evolve(
            original_macro=sample_macro,
            evolution_records=sample_evolution_records,
            step_results=[],
            target_platform="web"
        )

        assert "expansion_ratio" in metadata
        assert "modified_steps" in metadata
        assert "modification_rate" in metadata
        assert "transformations_applied" in metadata


class TestStepTransformers:
    """Test individual step transformers"""

    def test_coordinate_drift_transformer(self):
        """Test coordinate drift transformation"""
        transformer = CoordinateDriftTransformer()

        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "tap",
            "target_selector": "#btn",
            "payload": {"x": 100, "y": 200}
        }

        record = MacroEvolutionRecord(
            original_step=step,
            evolved_step=step,
            evolution_reason="coordinate_drift",
            confidence=0.9
        )

        context = EvolutionContext(
            original_macro=[step],
            step_results=[],
            evolution_records=[record],
            target_platform="android"
        )

        assert transformer.can_transform(step, record) is True

        evolved_steps = transformer.transform(step, record, context)

        assert len(evolved_steps) == 1
        evolved = evolved_steps[0]
        # Should have fallback or precondition
        assert "fallback" in evolved or "precondition" in evolved or "max_retries" in evolved.get("payload", {})

    def test_element_not_found_transformer(self):
        """Test element not found transformation"""
        transformer = ElementNotFoundTransformer()

        step = {
            "step_number": 1,
            "type": "action",
            "target_selector": "#submit",
            "payload": {"selector": "#submit"}
        }

        record = MacroEvolutionRecord(
            original_step=step,
            evolved_step=step,
            evolution_reason="element_not_found",
            confidence=0.8
        )

        context = EvolutionContext(
            original_macro=[step],
            step_results=[],
            evolution_records=[record],
            target_platform="web"
        )

        evolved_steps = transformer.transform(step, record, context)

        evolved = evolved_steps[0]
        payload = evolved.get("payload", {})
        # Should have selector_chain or scroll_to_find
        assert "selector_chain" in payload or "scroll_to_find" in payload or "selector_strategy" in payload

    def test_element_obscured_transformer(self):
        """Test element obscured transformation"""
        transformer = ElementObscuredTransformer()

        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "click",
            "source": "dom"
        }

        record = MacroEvolutionRecord(
            original_step=step,
            evolved_step=step,
            evolution_reason="element_obscured",
            confidence=0.9
        )

        context = EvolutionContext(
            original_macro=[step],
            step_results=[],
            evolution_records=[record],
            target_platform="web"
        )

        evolved_steps = transformer.transform(step, record, context)

        # Should expand to multiple steps (dismissal + wait + action)
        assert len(evolved_steps) >= 2

    def test_loading_timeout_transformer(self):
        """Test loading timeout transformation"""
        transformer = LoadingTimeoutTransformer()

        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "wait",
            "payload": {"duration_ms": 1000}
        }

        record = MacroEvolutionRecord(
            original_step=step,
            evolved_step=step,
            evolution_reason="loading_timeout",
            confidence=0.8
        )

        context = EvolutionContext(
            original_macro=[step],
            step_results=[],
            evolution_records=[record],
            target_platform="web"
        )

        evolved_steps = transformer.transform(step, record, context)

        evolved = evolved_steps[0]
        # Should convert to conditional wait or increase timeout
        assert evolved.get("event_type") == "wait_for" or evolved.get("payload", {}).get("timeout_ms", 0) > 1000

    def test_state_mismatch_transformer(self):
        """Test state mismatch transformation"""
        transformer = StateMismatchTransformer()

        step = {
            "step_number": 2,
            "type": "action",
            "event_type": "click"
        }

        record = MacroEvolutionRecord(
            original_step=step,
            evolved_step=step,
            evolution_reason="state_mismatch",
            confidence=0.75
        )

        context = EvolutionContext(
            original_macro=[
                {"step_number": 1, "event_type": "goto"},
                step
            ],
            step_results=[],
            evolution_records=[record],
            target_platform="web"
        )

        evolved_steps = transformer.transform(step, record, context)

        # Should add verification step before action
        assert len(evolved_steps) >= 2
        assert any(s.get("type") == "verify" for s in evolved_steps)


class TestEvolutionOptimizer:
    """Test evolution optimizer"""

    def test_merge_consecutive_waits(self):
        """Test merging consecutive wait steps"""
        optimizer = EvolutionOptimizer()

        macro = [
            {"step_number": 1, "event_type": "goto", "payload": {}},
            {"step_number": 2, "event_type": "wait", "payload": {"duration_ms": 1000}},
            {"step_number": 3, "event_type": "wait", "payload": {"duration_ms": 500}},
            {"step_number": 4, "event_type": "wait", "payload": {"duration_ms": 500}},
            {"step_number": 5, "event_type": "click", "payload": {}},
        ]

        optimized = optimizer.optimize(macro)

        # Should merge waits 2,3,4 into one
        assert len(optimized) < len(macro)

        # Find merged wait
        wait_steps = [s for s in optimized if s.get("event_type") == "wait"]
        assert len(wait_steps) == 1
        assert wait_steps[0]["payload"]["duration_ms"] == 2000  # 1000 + 500 + 500

    def test_remove_duplicate_verifications(self):
        """Test removing duplicate verification steps"""
        optimizer = EvolutionOptimizer()

        macro = [
            {"step_number": 1, "type": "action", "payload": {}},
            {"step_number": 2, "type": "verify", "payload": {"expected_state": {"page": "loaded"}}},
            {"step_number": 3, "type": "verify", "payload": {"expected_state": {"page": "loaded"}}},
            {"step_number": 4, "type": "action", "payload": {}},
        ]

        optimized = optimizer.optimize(macro)

        verify_steps = [s for s in optimized if s.get("type") == "verify"]
        assert len(verify_steps) == 1

    def test_renumbering_after_optimization(self):
        """Test that steps are renumbered after optimization"""
        optimizer = EvolutionOptimizer()

        macro = [
            {"step_number": 1, "event_type": "goto"},
            {"step_number": 2, "event_type": "wait"},
            {"step_number": 3, "event_type": "wait"},
            {"step_number": 4, "event_type": "click"},
        ]

        optimized = optimizer.optimize(macro)

        for i, step in enumerate(optimized, 1):
            assert step["step_number"] == i


class TestFallbackChain:
    """Test fallback chain generation"""

    def test_generate_fallback_chain(self):
        """Test generating fallback chain for a step"""
        engine = MacroEvolutionEngine()

        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "click",
            "target_selector": "#btn",
            "payload": {"selector": "#btn"}
        }

        chain = engine.generate_fallback_chain(step, max_fallbacks=3)

        assert len(chain) <= 3
        assert len(chain) >= 1

        # Each level should have increasing robustness
        for i, level in enumerate(chain):
            payload = level.get("payload", {})
            if i > 0:
                # Higher levels should have more fallback options
                assert "max_retries" in payload or "use_fuzzy_match" in payload or "fallback_type" in level
