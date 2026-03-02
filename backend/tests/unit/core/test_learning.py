"""
Unit tests for learning system.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.models.learning import LearnedSkill

# Check if we should skip DB-dependent tests (using sync connection)
def _check_db_sync():
    """Check if PostgreSQL database is available using sync connection."""
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("POSTGRES_SERVER", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ.get("POSTGRES_DB", "app"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "admin888"),
            connect_timeout=3
        )
        conn.close()
        return True
    except Exception:
        return False

DB_AVAILABLE = _check_db_sync()

skip_if_no_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="Database not available"
)


class TestSkillDiscovery:
    """Tests for SkillDiscovery.

    Note: The following tests are for legacy regex-based pattern matching.
    The current implementation uses LLM-based matching and these tests
    have been moved to integration tests with VCR recording.
    See: tests/integration/test_learning_discovery.py
    """

    @pytest.mark.skip(reason="Database-dependent test - requires full DB mock setup")
    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_exact_search_with_match(self):
        """Test exact search finding a match."""
        from app.core.learning.discovery import SkillDiscovery

        discovery = SkillDiscovery()

        # Mock the skill retrieval
        # Note: trigger_patterns should be user-friendly patterns like "test pattern {arg}"
        # NOT full regex like "^test pattern (?P<arg>.+)$"
        mock_skill = MagicMock(spec=LearnedSkill)
        mock_skill.id = 1
        mock_skill.name = "test_skill"
        mock_skill.trigger_patterns = json.dumps(["test pattern {arg}"])
        mock_skill.namespace = "test/ns"

        # Patch the class methods to avoid DB access
        with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
            with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
                match, skills, reasoning = await discovery.exact_search("test pattern value")

                assert match is not None
                assert match.skill_name == "test_skill"
                assert match.skill_id == 1
                assert match.confidence == 1.0
                assert match.extracted_params.get("arg") == "value"

    @pytest.mark.skip(reason="Database-dependent test - requires full DB mock setup")
    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_exact_search_no_match(self):
        """Test exact search with no match."""
        from app.core.learning.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        mock_skill = MagicMock(spec=LearnedSkill)
        mock_skill.id = 1
        mock_skill.name = "test_skill"
        mock_skill.trigger_patterns = json.dumps(["other pattern"])
        mock_skill.namespace = "test/ns"

        with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
            match, skills, reasoning = await discovery.exact_search("test pattern")

            assert match is None
            assert len(skills) == 0  # No namespace context, so no skills returned

    @pytest.mark.skip(reason="Database-dependent test - requires full DB mock setup")
    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_namespace_mounting(self):
        """Test mounting skills by namespace prefix."""
        from app.core.learning.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        mock_skills = [
            MagicMock(spec=LearnedSkill, namespace="os/macos/copy"),
            MagicMock(spec=LearnedSkill, namespace="os/macos/paste"),
            MagicMock(spec=LearnedSkill, namespace="os/windows/copy"),
        ]

        with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=mock_skills[:2])):
            match, skills, reasoning = await discovery.exact_search("any query", namespace_context="os/macos")

            # Should return macos skills even without pattern match
            assert len(skills) == 2
            assert all(s.namespace.startswith("os/macos") for s in skills)

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_match_wrapper(self):
        """Test match() wrapper for backward compatibility."""
        from app.core.learning.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        mock_skill = MagicMock(spec=LearnedSkill)
        mock_skill.id = 1
        mock_skill.name = "test_skill"
        mock_skill.trigger_patterns = json.dumps(["test pattern"])
        mock_skill.namespace = "test/ns"

        with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
            match = await discovery.match("test pattern", threshold=0.5, thread_id="thread_123")

            assert match is not None
            assert match.skill_name == "test_skill"

    @pytest.mark.skip(reason="Database-dependent test - requires full DB mock setup")
    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_retrieve_wrapper(self):
        """Test retrieve() wrapper for backward compatibility."""
        from app.core.learning.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        mock_skills = [
            MagicMock(spec=LearnedSkill, namespace="test/ns"),
        ]

        # retrieve calls exact_search which needs namespace_context to return skills
        # Use exact_search directly with namespace_context for the test
        with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=mock_skills)):
            _, skills, _ = await discovery.exact_search("test/ns", namespace_context="test/ns")

            assert len(skills) == 1


class TestSkillSynthesizer:
    """Tests for WorkflowSynthesizer."""

    @pytest.fixture
    def mock_trace_sequence(self):
        """Create a mock TraceSequence."""
        from app.core.learning.trace_parser import TraceSequence, TraceStep, ActionSource, ActionCategory

        sequence = TraceSequence(
            thread_id="thread_123",
            session_id="session_456",
            task_name="Test Task"
        )
        sequence.steps = [
            TraceStep(
                step_number=1,
                source=ActionSource.HUMAN,
                category=ActionCategory.QUERY,
                action_type="human_input",
                action_name="human_input",
                action_args={"content": "Create a file"},
            ),
            TraceStep(
                step_number=2,
                source=ActionSource.AGENT,
                category=ActionCategory.EDIT,
                action_type="tool_call",
                action_name="write_file",
                action_args={"path": "test.txt", "content": "hello"},
            ),
        ]
        sequence.tools_used = ["write_file"]
        return sequence

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_synthesize_from_trace(self, mock_trace_sequence):
        """Test synthesizing skill from execution trace."""
        from app.core.learning.skill_synthesizer import WorkflowSynthesizer

        thread_id = "thread_123"
        synthesizer = WorkflowSynthesizer(thread_id=thread_id, session_id="session_456")

        # Mock the parser and LLM
        mock_yaml_output = """
name: create_file
namespace: filesystem
description: Create a file with given content
trigger_patterns:
  - "Create a file named {{name}}"
parameters:
  - name: name
    type: string
    description: Name of the file
preconditions:
  - "Directory exists"
instructions: |
  Use write_file to create the file with the specified content.
"""

        with patch.object(synthesizer.parser, 'parse', new_callable=lambda: AsyncMock(return_value=mock_trace_sequence)):
            with patch.object(synthesizer, '_generate_skill_yaml', new_callable=lambda: AsyncMock(return_value=mock_yaml_output)):
                skill = await synthesizer.synthesize(auto_optimize=True)

                assert skill.name == "create_file"
                assert skill.namespace == "filesystem"
                assert skill.description == "Create a file with given content"
                assert "Create a file named {{name}}" in skill.trigger_patterns
                assert len(skill.parameters) == 1
                assert skill.parameters[0].name == "name"
                assert skill.source_thread_id == thread_id

    @pytest.mark.asyncio
    async def test_synthesize_empty_trace(self):
        """Test synthesizing with empty trace raises error."""
        from app.core.learning.skill_synthesizer import WorkflowSynthesizer
        from app.core.learning.trace_parser import TraceSequence

        thread_id = "thread_empty"
        synthesizer = WorkflowSynthesizer(thread_id=thread_id)

        empty_sequence = TraceSequence(thread_id=thread_id)
        empty_sequence.steps = []

        with patch.object(synthesizer.parser, 'parse', new_callable=lambda: AsyncMock(return_value=empty_sequence)):
            with pytest.raises(ValueError, match="No trace data found"):
                await synthesizer.synthesize()


class TestTraceParser:
    """Tests for trace parsing."""

    @pytest.fixture
    def parser(self):
        """Create a trace parser instance."""
        from app.core.learning.trace_parser import TraceParser

        return TraceParser(thread_id="thread_123", session_id="session_456")

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_parse_simple_trace(self, parser):
        """Test parsing a simple execution trace."""
        from app.core.learning.trace_parser import ActionSource, ActionCategory

        # Mock TraceEvent objects
        mock_events = [
            MagicMock(
                id=1,
                step_number=1,
                source="human",
                is_human_action=True,
                action_type="human_input",
                action_payload='{"content": "Hello"}',
                node_name="test_node",
                ui_element_info=None,
                screenshot_path=None,
                target_selector=None,
                target_text=None,
                state_snapshot=None,
                user_feedback=None,
                timestamp=1234567890.0,
            ),
            MagicMock(
                id=2,
                step_number=2,
                source="agent",
                is_human_action=False,
                action_type="llm_output",
                action_payload='{"content": "Hi there"}',
                node_name="test_node",
                ui_element_info=None,
                screenshot_path=None,
                target_selector=None,
                target_text=None,
                state_snapshot=None,
                user_feedback=None,
                timestamp=1234567891.0,
            ),
        ]

        with patch.object(parser, '_fetch_events', new_callable=lambda: AsyncMock(return_value=mock_events)):
            sequence = await parser.parse()

            assert len(sequence.steps) == 2
            assert sequence.steps[0].source == ActionSource.HUMAN
            assert sequence.steps[1].source == ActionSource.AGENT
            assert sequence.thread_id == "thread_123"

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_parse_with_tool_calls(self, parser):
        """Test parsing trace with tool calls."""
        from app.core.learning.trace_parser import ActionSource, ActionCategory

        mock_events = [
            MagicMock(
                id=1,
                step_number=1,
                source="agent",
                is_human_action=False,
                action_type="tool_call",
                action_payload='{"name": "read_file", "args": {"path": "test.py"}}',
                node_name="developer",
                ui_element_info=None,
                screenshot_path=None,
                target_selector=None,
                target_text=None,
                state_snapshot=None,
                user_feedback=None,
                timestamp=1234567890.0,
            ),
        ]

        with patch.object(parser, '_fetch_events', new_callable=lambda: AsyncMock(return_value=mock_events)):
            sequence = await parser.parse()

            assert len(sequence.steps) == 1
            assert sequence.steps[0].action_name == "read_file"
            assert sequence.steps[0].action_args == {"path": "test.py"}
            assert sequence.steps[0].category == ActionCategory.QUERY

    def test_to_narrative(self, parser):
        """Test converting sequence to narrative."""
        from app.core.learning.trace_parser import TraceSequence, TraceStep, ActionSource, ActionCategory

        sequence = TraceSequence(
            thread_id="thread_123",
            task_name="Test Task"
        )
        sequence.steps = [
            TraceStep(
                step_number=1,
                source=ActionSource.HUMAN,
                category=ActionCategory.QUERY,
                action_type="human_input",
                action_name="human_input",
                action_args={"content": "Hello"},
            ),
        ]

        narrative = parser.to_narrative(sequence)

        assert "Test Task" in narrative
        assert "thread_123" in narrative
        assert "Step 1" in narrative
        assert "human_input" in narrative


class TestSkillValidator:
    """Tests for skill validation."""

    @pytest.fixture
    def valid_skill_folder(self, tmp_path):
        """Create a valid skill folder structure."""
        skill_folder = tmp_path / "test_skill"
        skill_folder.mkdir()

        skill_md = skill_folder / "SKILL.md"
        skill_md.write_text("""---
name: valid_skill
description: A valid test skill
trigger_patterns:
  - "Valid pattern {{arg}}"
parameters:
  - name: arg
    type: string
    description: An argument
preconditions:
  - "Environment ready"
---

# Valid Skill

This is a valid skill with instructions.
""")
        return skill_folder

    @pytest.fixture
    def invalid_skill_folder(self, tmp_path):
        """Create an invalid skill folder (missing required fields)."""
        skill_folder = tmp_path / "invalid_skill"
        skill_folder.mkdir()

        skill_md = skill_folder / "SKILL.md"
        skill_md.write_text("""---
description: Missing name field
trigger_patterns: []
---

# Invalid Skill
""")
        return skill_folder

    def test_validate_valid_skill(self, valid_skill_folder):
        """Test validating a correct skill folder structure."""
        from app.core.learning.skill_validator import SkillValidator

        result = SkillValidator.validate_folder(valid_skill_folder)

        assert result.is_valid is True
        assert result.status == "healthy"
        assert len(result.errors) == 0
        assert result.metadata is not None
        assert result.metadata.get("name") == "valid_skill"

    def test_validate_missing_required_field(self, invalid_skill_folder):
        """Test validating skill missing required field."""
        from app.core.learning.skill_validator import SkillValidator

        result = SkillValidator.validate_folder(invalid_skill_folder)

        assert result.is_valid is False
        assert result.status == "error"
        assert any("name" in error.lower() for error in result.errors)

    def test_validate_missing_skill_md(self, tmp_path):
        """Test validating folder without SKILL.md."""
        from app.core.learning.skill_validator import SkillValidator

        empty_folder = tmp_path / "empty_skill"
        empty_folder.mkdir()

        result = SkillValidator.validate_folder(empty_folder)

        assert result.is_valid is False
        assert result.status == "error"
        assert any("SKILL.md" in error for error in result.errors)

    def test_validate_nonexistent_folder(self, tmp_path):
        """Test validating a non-existent folder."""
        from app.core.learning.skill_validator import SkillValidator

        nonexistent = tmp_path / "does_not_exist"

        result = SkillValidator.validate_folder(nonexistent)

        assert result.is_valid is False
        assert result.status == "error"
        assert len(result.errors) == 1

    def test_validate_with_clutter(self, valid_skill_folder):
        """Test validating skill folder with clutter files."""
        from app.core.learning.skill_validator import SkillValidator

        # Add a clutter file
        readme = valid_skill_folder / "README.md"
        readme.write_text("# README")

        result = SkillValidator.validate_folder(valid_skill_folder)

        assert result.is_valid is True
        assert result.status == "warning"
        assert any("README.md" in warning for warning in result.warnings)

    def test_validate_invalid_yaml_frontmatter(self, tmp_path):
        """Test validating skill with invalid YAML frontmatter."""
        from app.core.learning.skill_validator import SkillValidator

        skill_folder = tmp_path / "bad_yaml_skill"
        skill_folder.mkdir()

        skill_md = skill_folder / "SKILL.md"
        skill_md.write_text("Not a valid SKILL.md file without frontmatter")

        result = SkillValidator.validate_folder(skill_folder)

        assert result.is_valid is False
        assert result.status == "error"
        assert any("frontmatter" in error.lower() for error in result.errors)
