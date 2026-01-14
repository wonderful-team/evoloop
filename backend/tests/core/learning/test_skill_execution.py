from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.core.learning.skill_executor import SkillExecutor, SkillMatcher
from app.infrastructure.database.sql.models import LearnedSkill

# ==========================================
# SkillMatcher Tests
# ==========================================

@pytest.fixture
def mock_skills():
    return [
        LearnedSkill(
            id=1,
            name="search_file",
            description="Search for a file",
            trigger_patterns='["find file {filename}", "search code for {query}"]',
            steps='[]',
            is_active=True
        ),
        LearnedSkill(
            id=2,
            name="run_test",
            description="Run a specific test",
            trigger_patterns='["run test {test_name}"]',
            steps='[]',
            is_active=True
        )
    ]

@pytest.mark.anyio
async def test_pattern_to_regex():
    matcher = SkillMatcher()

    # Test 1: Simple parameter
    pattern = "find file {filename}"
    regex = matcher._pattern_to_regex(pattern)
    # Expected: "^find\ file\ (?P<filename>.+?)$" (with escaping)
    assert "(?P<filename>.+?)" in regex
    assert regex.startswith("^")
    assert regex.endswith("$")

    # Test 2: Multiple parameters
    pattern = "replace {old} with {new}"
    regex = matcher._pattern_to_regex(pattern)
    assert "(?P<old>.+?)" in regex
    assert "(?P<new>.+?)" in regex

@pytest.mark.anyio
async def test_regex_match(mock_skills):
    matcher = SkillMatcher()

    # Mock _load_skills to avoid DB access
    with patch.object(matcher, '_load_skills', new=AsyncMock(return_value=mock_skills)):
        # Exact match
        result = await matcher.match("find file main.py")
        assert result is not None
        assert result.skill_id == 1
        assert result.extracted_params["filename"] == "main.py"
        assert result.confidence > 0.9

        # Second pattern match
        result = await matcher.match("search code for definition")
        assert result is not None
        assert result.skill_id == 1
        assert result.extracted_params["query"] == "definition"

        # Another skill
        result = await matcher.match("run test test_api.py")
        assert result is not None
        assert result.skill_id == 2
        assert result.extracted_params["test_name"] == "test_api.py"

@pytest.mark.anyio
async def test_semantic_match_fallback(mock_skills):
    matcher = SkillMatcher()

    # Mock LLM for semantic match
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(
        content='{"skill_id": 1, "skill_name": "search_file", "confidence": 0.8, "params": {"filename": "config.py"}}'
    )

    with patch.object(matcher, '_load_skills', new=AsyncMock(return_value=mock_skills)):
        with patch('app.core.learning.skill_executor.LLMFactory.create_llm', return_value=mock_llm):
            # Input that doesn't match regex but matches semantically
            result = await matcher.match("I need to locate config.py")

            assert result is not None
            assert result.skill_id == 1
            assert result.extracted_params["filename"] == "config.py"
            assert result.confidence == 0.8

# ==========================================
# SkillExecutor Tests
# ==========================================

def test_param_substitution():
    executor = SkillExecutor()

    args = {
        "path": "src/{filename}",
        "query": "{{query}}",
        "static": "value"
    }

    params = {
        "filename": "app.py",
        "query": "class User"
    }

    # Standard param substitution
    resolved = executor._substitute_params(args, params)

    # Note: currently the implementation does specific {{param}} replacement in values,
    # NOT path interpolation like "src/{filename}" unless that was explicitly regexed/handled.
    # Let's check the implementation logic:
    # value.replace(f"{{{{{param_name}}}}}", str(param_value))

    assert resolved["query"] == "class User"
    assert resolved["static"] == "value"

    # Test result substitution
    previous_result = {"status": "ok", "id": 123}
    args_with_result = {"prev_id": "{{result.id}}"}

    resolved_res = executor._substitute_params(args_with_result, {}, previous_result)
    assert resolved_res["prev_id"] == "123"

@pytest.mark.anyio
async def test_execute_skill_success():
    executor = SkillExecutor()

    # Mock skill data
    mock_skill = LearnedSkill(
        id=1,
        name="test_skill",
        steps='[{"action": "read_file", "args": {"path": "{{filepath}}"}}]',
        success_count=0,
        failure_count=0
    )

    # Mock tool executor
    executor.tool_executor = AsyncMock()
    executor.tool_executor.execute.return_value = "File content"

    # Mock DB session
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_skill

    # Create a mock session context manager
    mock_session_scope = MagicMock()
    mock_session_scope.__aenter__.return_value = mock_db
    mock_session_scope.__aexit__.return_value = None

    with patch('app.core.learning.skill_executor.session_scope', return_value=mock_session_scope):
        tool_registry = {"read_file": MagicMock()}

        success, summary = await executor.execute_skill(
            skill_id=1,
            params={"filepath": "main.py"},
            tool_registry=tool_registry
        )

        assert success is True
        assert "Success" in summary

        # Verify tool called with substituted params
        executor.tool_executor.execute.assert_called_once()
        call_args = executor.tool_executor.execute.call_args
        assert call_args[0][1]["path"] == "main.py"

        # Verify DB update (success count)
        assert mock_skill.success_count == 1
