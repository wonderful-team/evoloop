"""
Unit tests for EditEngine cascading strategies.

These tests validate the "fuzzy by default" upgrade.
pytest tests/unit/domain/tools/test_edit_engine_strategies.py -v
"""

import pytest

from app.domain.tools.utils.editing.engine import EditEngine
from app.domain.tools.utils.editing.strategies import STRATEGIES


class TestEditEngineStrategies:
    """Validate that EditEngine correctly cascades through all 9 strategies."""

    @pytest.fixture
    def sample_content(self):
        return '''def helper(data: str) -> str:
    if not data:
        return ""
    result = data.strip()
    return result.upper()
'''

    def test_simple_replacer_is_first_strategy(self):
        """Strategy 0 must be simple_replacer (exact match)."""
        assert len(STRATEGIES) == 9
        assert STRATEGIES[0].__name__ == "simple_replacer"

    def test_exact_match_uses_simple_replacer(self, sample_content):
        target = "    result = data.strip()"
        replacement = "    result = data.strip().lower()"
        success, new_content, log = EditEngine.apply_replacement(
            sample_content, target, replacement
        )
        assert success is True
        assert "simple_replacer" in log.lower()
        assert "    result = data.strip().lower()" in new_content

    def test_line_trimmed_replacer(self, sample_content):
        """Target with extra leading/trailing spaces on lines."""
        target = "    result = data.strip()  "  # trailing spaces
        replacement = "    result = data.strip().lower()"
        success, new_content, log = EditEngine.apply_replacement(
            sample_content, target, replacement
        )
        assert success is True
        assert "line_trimmed" in log.lower() or "simple" in log.lower()

    def test_whitespace_normalized_replacer(self, sample_content):
        """Target with trailing whitespace differences."""
        content = "def foo():\n    pass \n"  # trailing space after pass
        target = "    pass"  # no trailing space in target
        replacement = "    return"
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement
        )
        assert success is True
        # Should match via line_trimmed or simple (if exact match exists without trailing space)
        # Note: If exact match fails, line_trimmed should catch it
        matched = any(s in log.lower() for s in [
            "line_trimmed", "whitespace_normalized", "simple"
        ])
        assert matched, f"Unexpected strategy log: {log}"

    def test_indentation_flexible_replacer(self):
        """Tab indentation vs 4-space indentation."""
        content = "def foo():\n\tpass\n"
        target = "    pass"  # 4 spaces
        replacement = "    return"
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement
        )
        assert success is True
        assert "indentation" in log.lower() or "simple" in log.lower() or "line_trimmed" in log.lower()

    def test_block_anchor_levenshtein(self):
        """Fuzzy block match with minor differences."""
        content = '''class Config:
    def __init__(self):
        self.debug = True
        self.timeout = 30
        self.verbose = False
'''
        target = '''    def __init__(self):
        self.debug = False
        self.timeout = 30
        self.verbose = False'''
        replacement = '''    def __init__(self):
        self.debug = False
        self.timeout = 60
        self.verbose = False'''
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement
        )
        assert success is True
        assert "block_anchor" in log.lower() or "simple" in log.lower()
        assert "self.timeout = 60" in new_content

    def test_context_aware_replacer(self):
        """Match using surrounding context when exact block is ambiguous."""
        content = '''def a():
    return True

def b():
    return True
'''
        target = '''def b():
    return True'''
        replacement = '''def b():
    return False'''
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement
        )
        assert success is True
        assert "return False" in new_content

    def test_multi_occurrence_replacer(self):
        """Replace all occurrences when replace_all=True."""
        content = '''def a():
    return True

def b():
    return True
'''
        target = "    return True"
        replacement = "    return False"
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement, replace_all=True
        )
        assert success is True
        assert new_content.count("return False") == 2
        assert new_content.count("return True") == 0

    def test_all_strategies_exhausted(self, sample_content):
        """Completely unrelated target should fail."""
        target = "this string does not exist anywhere"
        replacement = "replacement"
        success, new_content, log = EditEngine.apply_replacement(
            sample_content, target, replacement
        )
        assert success is False
        assert new_content == sample_content

    def test_replace_all_partial_match_behavior(self):
        """If replace_all=True and some occurrences can't match, behavior should be deterministic."""
        content = '''x = 1
y = 1
z = 2
'''
        target = "1"
        replacement = "99"
        success, new_content, log = EditEngine.apply_replacement(
            content, target, replacement, replace_all=True
        )
        # Since "1" appears in "x = 1" and "y = 1", and both are exact matches,
        # it should replace all occurrences.
        assert success is True
        assert "x = 99" in new_content
        assert "y = 99" in new_content
        assert "z = 2" in new_content

    def test_strategy_order_is_stable(self):
        """Ensure the 9 strategies are in the expected order."""
        expected_names = [
            "simple_replacer",
            "line_trimmed_replacer",
            "block_anchor_replacer",
            "whitespace_normalized_replacer",
            "trimmed_boundary_replacer",
            "escape_normalized_replacer",
            "context_aware_replacer",
            "indentation_flexible_replacer",
            "multi_occurrence_replacer",
        ]
        actual_names = [s.__name__ for s in STRATEGIES]
        assert actual_names == expected_names
