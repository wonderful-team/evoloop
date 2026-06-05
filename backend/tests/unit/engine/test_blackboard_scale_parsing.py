"""
Tests for BlackboardParser parsing arbitrary [BLACKBOARD: key=value] tags.

Verifies that the parser correctly extracts scalar key=value pairs
and stores them in blackboard metadata via DynamicBaseModel(extra="allow").
"""

import pytest

from app.core.engine.blackboard_parser import BlackboardParser
from app.core.engine.state.blackboard import BlackboardState, BlackboardMetadata


class TestBlackboardParserGeneric:
    """Tests for generic blackboard tag parsing."""

    def test_parse_string_field(self):
        """[BLACKBOARD: tier=large] should be parsed as string."""
        content = "Assessment complete. [BLACKBOARD: tier=large]"
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.tier == "large"

    def test_parse_integer_field(self):
        """[BLACKBOARD: budget=25] should be parsed as integer."""
        content = "Budget set. [BLACKBOARD: budget=25]"
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.budget == 25
        assert isinstance(result.metadata.budget, int)

    def test_parse_multiple_fields(self):
        """Multiple blackboard tags in one response."""
        content = (
            "Assessment done. "
            "[BLACKBOARD: tier=large] "
            "[BLACKBOARD: budget=25]"
        )
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.tier == "large"
        assert result.metadata.budget == 25

    def test_parse_boolean_true(self):
        """[BLACKBOARD: flag=true] should be parsed as bool."""
        content = "Flag set. [BLACKBOARD: flag=true]"
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.flag is True

    def test_parse_boolean_false(self):
        """[BLACKBOARD: flag=false] should be parsed as bool."""
        content = "Flag cleared. [BLACKBOARD: flag=false]"
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.flag is False

    def test_no_tags_returns_copy(self):
        """No tags in content returns a copy of the blackboard."""
        content = "No tags here."
        blackboard = BlackboardState(metadata=BlackboardMetadata())

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata == blackboard.metadata

    def test_preserve_existing_metadata(self):
        """Parsing should preserve existing metadata fields."""
        content = "[BLACKBOARD: new_field=hello]"
        metadata = BlackboardMetadata(tool_history=["read_file", "list_dir"])
        blackboard = BlackboardState(metadata=metadata)

        result = BlackboardParser.parse(content, blackboard)

        assert result.metadata.new_field == "hello"
        assert result.metadata.tool_history == ["read_file", "list_dir"]
