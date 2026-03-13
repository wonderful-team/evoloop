"""
Tests for MacroOptimizer - covering bugs found in code review.

Bugs to test:
1. _remove_duplicate_actions with small deduped list (index issue)
2. _is_duplicate_action edge cases
"""

import pytest
from unittest.mock import MagicMock


class TestMacroOptimizerRemoveDuplicates:
    """Test _remove_duplicate_actions method - Bug #6."""

    @pytest.fixture
    def optimizer(self):
        from app.core.execution.macro.optimizer import MacroOptimizer
        return MacroOptimizer()

    def test_remove_duplicates_with_fewer_steps_than_window(self, optimizer):
        """Bug #6: Test that dedup works when list has fewer items than DUPLICATE_DETECTION_WINDOW."""
        # Only 2 steps, but DUPLICATE_DETECTION_WINDOW is 3
        steps = [
            {"step_number": 1, "type": "action", "event_type": "click", "target_selector": "#btn1"},
            {"step_number": 2, "type": "action", "event_type": "click", "target_selector": "#btn2"},
        ]

        # Should not raise IndexError or other exceptions
        result, removed = optimizer._remove_duplicate_actions(steps)

        # Both should be kept since they're different
        assert len(result) == 2
        assert removed == 0

    def test_remove_duplicates_with_empty_list(self, optimizer):
        """Test dedup with empty list."""
        steps = []

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 0
        assert removed == 0

    def test_remove_duplicates_exact_same_action(self, optimizer):
        """Test removing exact duplicate actions."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "click", "target_selector": "#btn", "payload": {}},
            {"step_number": 2, "type": "action", "event_type": "click", "target_selector": "#btn", "payload": {}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 1
        assert removed == 1
        assert result[0]["step_number"] == 1

    def test_remove_duplicates_click_with_coordinates(self, optimizer):
        """Test dedup considering click coordinates."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "click", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "click", "payload": {"x": 0.51, "y": 0.51}},  # Within tolerance (0.01)
            {"step_number": 3, "type": "action", "event_type": "click", "payload": {"x": 0.8, "y": 0.8}},  # Different (> 0.01 away)
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        # Steps 1 and 2 are NOT considered duplicates because |0.51 - 0.5| = 0.01 is NOT < 0.01
        # The condition uses < 0.01, not <= 0.01
        # So all 3 steps should remain
        assert len(result) == 3
        assert removed == 0

    def test_remove_duplicates_click_within_tolerance(self, optimizer):
        """Test dedup when coordinates are truly within tolerance."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "click", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "click", "payload": {"x": 0.505, "y": 0.505}},  # Within 0.01 tolerance
            {"step_number": 3, "type": "action", "event_type": "click", "payload": {"x": 0.8, "y": 0.8}},  # Different
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        # Steps 1 and 2 ARE considered duplicates (|0.505 - 0.5| = 0.005 < 0.01)
        assert len(result) == 2
        assert removed == 1

    def test_remove_duplicates_click_with_different_modifiers(self, optimizer):
        """Test that clicks with different modifiers are not duplicates."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "click", "payload": {"x": 0.5, "y": 0.5, "button": "left"}},
            {"step_number": 2, "type": "action", "event_type": "click", "payload": {"x": 0.5, "y": 0.5, "button": "right"}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        # Both should be kept (different buttons)
        assert len(result) == 2
        assert removed == 0

    def test_remove_duplicates_input_with_different_text(self, optimizer):
        """Test that inputs with different text are not duplicates."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "input", "payload": {"text": "hello"}},
            {"step_number": 2, "type": "action", "event_type": "input", "payload": {"text": "world"}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 2
        assert removed == 0

    def test_remove_duplicates_input_with_same_text(self, optimizer):
        """Test removing duplicate inputs with same text."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "input", "payload": {"text": "hello", "clear_first": True}},
            {"step_number": 2, "type": "action", "event_type": "input", "payload": {"text": "hello", "clear_first": True}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 1
        assert removed == 1

    def test_remove_duplicates_navigate_same_url(self, optimizer):
        """Test removing duplicate navigations to same URL."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "navigate", "payload": {"url": "https://example.com"}},
            {"step_number": 2, "type": "action", "event_type": "navigate", "payload": {"url": "https://example.com"}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 1
        assert removed == 1

    def test_remove_duplicates_navigate_different_url(self, optimizer):
        """Test that navigations to different URLs are kept."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "navigate", "payload": {"url": "https://example.com"}},
            {"step_number": 2, "type": "action", "event_type": "navigate", "payload": {"url": "https://other.com"}},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        assert len(result) == 2
        assert removed == 0

    def test_remove_duplicates_non_action_types_ignored(self, optimizer):
        """Test that non-action types (extract, dump) are not checked for duplicates."""
        steps = [
            {"step_number": 1, "type": "extract", "extract_type": "get_text", "key": "data_1"},
            {"step_number": 2, "type": "extract", "extract_type": "get_text", "key": "data_2"},
        ]

        result, removed = optimizer._remove_duplicate_actions(steps)

        # Both should be kept (extract types are not deduplicated in this pass)
        assert len(result) == 2
        assert removed == 0


class TestMacroOptimizerIsDuplicateAction:
    """Test _is_duplicate_action method edge cases."""

    @pytest.fixture
    def optimizer(self):
        from app.core.execution.macro.optimizer import MacroOptimizer
        return MacroOptimizer()

    def test_is_duplicate_with_empty_previous(self, optimizer):
        """Test checking duplicate against empty list."""
        step = {"type": "action", "event_type": "click", "payload": {}}
        result = optimizer._is_duplicate_action(step, [])
        assert result is False

    def test_is_duplicate_open_app_same_package(self, optimizer):
        """Test open_app duplicate detection by package."""
        step = {"type": "action", "event_type": "open_app", "payload": {"package": "com.example.app"}}
        previous = [{"type": "action", "event_type": "open_app", "payload": {"package": "com.example.app"}}]

        result = optimizer._is_duplicate_action(step, previous)
        assert result is True

    def test_is_duplicate_open_app_all_fields_different(self, optimizer):
        """Test open_app when ALL fields (package, app_name, text) are different."""
        # Note: The current implementation checks package OR app_name OR text
        # If all three are different, it's NOT a duplicate
        step = {"type": "action", "event_type": "open_app", "payload": {
            "package": "com.example.app",
            "app_name": "MyApp",
            "text": "Option1"
        }}
        previous = [{"type": "action", "event_type": "open_app", "payload": {
            "package": "com.other.app",
            "app_name": "OtherApp",
            "text": "Option2"
        }}]

        result = optimizer._is_duplicate_action(step, previous)
        # Different package AND different app_name AND different text, so NOT a duplicate
        assert result is False

    def test_is_duplicate_open_app_partial_match_considered_dup(self, optimizer):
        """Test that open_app is considered dup if ANY field matches (current behavior)."""
        # This reveals a potential bug: if app_name matches but package is different,
        # it's still considered a duplicate because the code uses OR logic
        step = {"type": "action", "event_type": "open_app", "payload": {"package": "com.different.app", "app_name": "WeChat"}}
        previous = [{"type": "action", "event_type": "open_app", "payload": {"package": "com.other.app", "app_name": "WeChat"}}]

        result = optimizer._is_duplicate_action(step, previous)
        # This is the CURRENT behavior - considered duplicate because app_name matches
        # This may be a bug - should probably require ALL fields to match
        assert result is True

    def test_is_duplicate_open_app_by_app_name(self, optimizer):
        """Test open_app duplicate detection by app_name."""
        step = {"type": "action", "event_type": "open_app", "payload": {"app_name": "WeChat"}}
        previous = [{"type": "action", "event_type": "open_app", "payload": {"app_name": "WeChat"}}]

        result = optimizer._is_duplicate_action(step, previous)
        assert result is True

    def test_is_duplicate_with_non_action_previous(self, optimizer):
        """Test that previous non-action steps are skipped."""
        step = {"type": "action", "event_type": "click", "payload": {}}
        previous = [
            {"type": "extract", "extract_type": "get_text"},  # Not an action
            {"type": "action", "event_type": "click", "payload": {}}  # This matches
        ]

        result = optimizer._is_duplicate_action(step, previous)
        assert result is True

    def test_is_duplicate_normalizes_payload(self, optimizer):
        """Test that timestamp and random_id are excluded from comparison."""
        step = {
            "type": "action",
            "event_type": "custom_action",
            "payload": {"data": "value", "timestamp": 123}
        }
        previous = [{
            "type": "action",
            "event_type": "custom_action",
            "payload": {"data": "value", "timestamp": 456}  # Different timestamp
        }]

        result = optimizer._is_duplicate_action(step, previous)
        assert result is True  # Should be considered duplicate (timestamp excluded)


class TestMacroOptimizerMergeWaits:
    """Test _merge_wait_steps method."""

    @pytest.fixture
    def optimizer(self):
        from app.core.execution.macro.optimizer import MacroOptimizer
        return MacroOptimizer()

    def test_merge_consecutive_waits(self, optimizer):
        """Test merging multiple consecutive wait steps."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 200}},
            {"step_number": 3, "type": "action", "event_type": "wait", "payload": {"duration_ms": 300}},
        ]

        result, merge_count, time_saved = optimizer._merge_wait_steps(steps)

        assert len(result) == 1
        assert result[0]["payload"]["duration_ms"] == 600  # Sum of all waits
        assert merge_count == 2  # 3 steps merged into 1

    def test_merge_with_max_wait_cap(self, optimizer):
        """Test that waits are capped at MAX_WAIT_DURATION_MS."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "wait", "payload": {"duration_ms": 3000}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 3000}},
        ]

        result, merge_count, time_saved = optimizer._merge_wait_steps(steps)

        # Should be capped at 5000ms (MAX_WAIT_DURATION_MS)
        assert result[0]["payload"]["duration_ms"] == 5000
        assert time_saved > 0  # 6000 - 5000 = 1000ms saved

    def test_single_short_wait_extended_to_min(self, optimizer):
        """Test that single short wait is extended to MIN_WAIT_DURATION_MS."""
        steps = [
            {"step_number": 1, "type": "action", "event_type": "wait", "payload": {"duration_ms": 50}},
        ]

        result, merge_count, time_saved = optimizer._merge_wait_steps(steps)

        # Should be extended to 100ms (MIN_WAIT_DURATION_MS)
        assert result[0]["payload"]["duration_ms"] == 100
        assert time_saved < 0  # Negative means time was added


class TestMacroOptimizerFilterRedundant:
    """Test _filter_redundant_actions method."""

    @pytest.fixture
    def optimizer(self):
        from app.core.execution.macro.optimizer import MacroOptimizer
        return MacroOptimizer()

    def test_filter_mouse_move(self, optimizer):
        """Test that mouse_move actions are filtered out."""
        steps = [
            {"step_number": 1, "event_type": "mouse_move", "payload": {"x": 100, "y": 200}},
            {"step_number": 2, "event_type": "click", "payload": {}},
        ]

        result = optimizer._filter_redundant_actions(steps)

        assert len(result) == 1
        assert result[0]["event_type"] == "click"

    def test_filter_cursor_move(self, optimizer):
        """Test that cursor_move actions are filtered out."""
        steps = [
            {"step_number": 1, "event_type": "cursor_move", "payload": {}},
            {"step_number": 2, "event_type": "hover", "payload": {}},  # Also low value
            {"step_number": 3, "event_type": "click", "payload": {}},
        ]

        result = optimizer._filter_redundant_actions(steps)

        assert len(result) == 1
        assert result[0]["event_type"] == "click"

    def test_filter_invalid_wait_zero_duration(self, optimizer):
        """Test that wait with 0 duration is filtered."""
        steps = [
            {"step_number": 1, "type": "wait", "payload": {"duration_ms": 0}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},
        ]

        result = optimizer._filter_redundant_actions(steps)

        assert len(result) == 1
        assert result[0]["payload"]["duration_ms"] == 100

    def test_filter_invalid_wait_negative_duration(self, optimizer):
        """Test that wait with negative duration is filtered."""
        steps = [
            {"step_number": 1, "type": "wait", "payload": {"duration_ms": -100}},
            {"step_number": 2, "event_type": "click", "payload": {}},
        ]

        result = optimizer._filter_redundant_actions(steps)

        assert len(result) == 1
        assert result[0]["event_type"] == "click"


class TestMacroOptimizerCoalesceExtracts:
    """Test _coalesce_extract_operations method."""

    @pytest.fixture
    def optimizer(self):
        from app.core.execution.macro.optimizer import MacroOptimizer
        return MacroOptimizer()

    def test_coalesce_multiple_extracts(self, optimizer):
        """Test merging consecutive extract operations."""
        steps = [
            {"step_number": 1, "type": "extract", "extract_type": "get_text", "key": "data_1"},
            {"step_number": 2, "type": "extract", "extract_type": "get_text", "key": "data_2"},
            {"step_number": 3, "type": "extract", "extract_type": "get_html", "key": "data_3"},
        ]

        result, coalesce_count = optimizer._coalesce_extract_operations(steps)

        assert len(result) == 1
        assert result[0]["type"] == "extract"
        assert result[0]["extract_type"] == "get_text"  # Uses first extract's type
        assert result[0]["payload"]["batch"] == True
        assert result[0]["payload"]["keys"] == ["data_1", "data_2", "data_3"]
        assert coalesce_count == 2  # 3 steps merged into 1

    def test_single_extract_unchanged(self, optimizer):
        """Test that single extract step is not modified."""
        steps = [
            {"step_number": 1, "type": "extract", "extract_type": "get_text", "key": "data_1"},
        ]

        result, coalesce_count = optimizer._coalesce_extract_operations(steps)

        assert len(result) == 1
        assert result[0]["extract_type"] == "get_text"  # Unchanged
        assert coalesce_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
