"""
Integration tests for SkillDiscovery with LLM-based matching.
Uses VCR.py to record and replay LLM responses.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import vcr

from app.models.learning import LearnedSkill


# Configure VCR for LLM API recording
def scrub_api_key(request):
    """Remove API keys from recorded requests."""
    if 'authorization' in request.headers:
        request.headers['authorization'] = 'Bearer <SCRUBBED>'
    if 'x-api-key' in request.headers:
        request.headers['x-api-key'] = '<SCRUBBED>'
    return request


my_vcr = vcr.VCR(
    cassette_library_dir='tests/fixtures/cassettes',
    record_mode=os.environ.get('VCR_RECORD_MODE', 'once'),
    match_on=['uri', 'method'],
    filter_headers=['authorization', 'x-api-key'],
    before_record_request=scrub_api_key,
    decode_compressed_response=True,
)


@pytest.mark.integration
@pytest.mark.asyncio
@my_vcr.use_cassette('skill_discovery_exact_match.yaml')
async def test_exact_search_with_match():
    """Test LLM-based exact search finding a match.

    This test uses VCR to record/replay LLM responses.
    To re-record: VCR_RECORD_MODE=rewrite uv run pytest tests/integration/test_learning_discovery.py::test_exact_search_with_match -v
    """
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()

    # Create mock skills for the catalog
    mock_skill = MagicMock(spec=LearnedSkill)
    mock_skill.id = 1
    mock_skill.name = "test_skill"
    mock_skill.description = "A test skill for unit testing"
    mock_skill.trigger_patterns = json.dumps(["test pattern {arg}"])
    mock_skill.namespace = "test/ns"

    # Patch skill retrieval to avoid DB access
    with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
        with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
            match, skills, reasoning = await discovery.exact_search("test pattern value")

            # Verify match results
            assert match is not None, f"Expected match but got None. Reasoning: {reasoning}"
            assert match.skill_name == "test_skill"
            assert match.skill_id == 1
            assert match.confidence > 0.5  # LLM should have reasonable confidence
            print(f"Match found: {match.skill_name} with confidence {match.confidence}")
            print(f"Reasoning: {reasoning}")


@pytest.mark.integration
@pytest.mark.asyncio
@my_vcr.use_cassette('skill_discovery_no_match.yaml')
async def test_exact_search_no_match():
    """Test LLM-based search with no match.

    This test uses VCR to record/replay LLM responses.
    To re-record: VCR_RECORD_MODE=rewrite uv run pytest tests/integration/test_learning_discovery.py::test_exact_search_no_match -v
    """
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()

    mock_skill = MagicMock(spec=LearnedSkill)
    mock_skill.id = 1
    mock_skill.name = "unrelated_skill"
    mock_skill.description = "A completely different skill"
    mock_skill.trigger_patterns = json.dumps(["other pattern"])
    mock_skill.namespace = "test/ns"

    with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
        with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=[])):
            match, skills, reasoning = await discovery.exact_search("completely unrelated query xyz123")

            # Should not find a match for unrelated query
            assert match is None or match.confidence < 0.5
            print(f"No match as expected. Reasoning: {reasoning}")


@pytest.mark.integration
@pytest.mark.asyncio
@my_vcr.use_cassette('skill_discovery_namespace.yaml')
async def test_namespace_mounting():
    """Test namespace-based skill mounting.

    This test uses VCR to record/replay LLM responses.
    To re-record: VCR_RECORD_MODE=rewrite uv run pytest tests/integration/test_learning_discovery.py::test_namespace_mounting -v
    """
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()

    mock_skills = [
        MagicMock(spec=LearnedSkill, id=1, name="macos_copy", namespace="os/macos/copy", description="Copy on macOS"),
        MagicMock(spec=LearnedSkill, id=2, name="macos_paste", namespace="os/macos/paste", description="Paste on macOS"),
        MagicMock(spec=LearnedSkill, id=3, name="windows_copy", namespace="os/windows/copy", description="Copy on Windows"),
    ]

    # Mock _get_active_skills to return only the macOS skills
    # This simulates having only os/macos skills in the active catalog
    # Use unique query with UUID to avoid cache collisions
    import uuid
    unique_query = f"copy file to clipboard {uuid.uuid4().hex[:8]}"
    with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=mock_skills[:2])):
        match, skills, reasoning = await discovery.exact_search(unique_query, namespace_context="os/macos")

        # When there's a match, should return the matched skill
        # When no match but namespace_context provided, returns all active skills
        assert len(skills) >= 1
        assert all(s.namespace.startswith("os/macos") for s in skills)
        print(f"Found {len(skills)} skills in namespace")


@pytest.mark.integration
@pytest.mark.asyncio
@my_vcr.use_cassette('skill_discovery_match_wrapper.yaml')
async def test_match_wrapper():
    """Test match() wrapper for backward compatibility.

    This test uses VCR to record/replay LLM responses.
    To re-record: VCR_RECORD_MODE=rewrite uv run pytest tests/integration/test_learning_discovery.py::test_match_wrapper -v
    """
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()

    mock_skill = MagicMock(spec=LearnedSkill)
    mock_skill.id = 1
    mock_skill.name = "test_skill"
    mock_skill.description = "A test skill"
    mock_skill.trigger_patterns = json.dumps(["test pattern"])
    mock_skill.namespace = "test/ns"

    with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
        with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=[mock_skill])):
            match = await discovery.match("test pattern", threshold=0.5, thread_id="thread_123")

            assert match is not None
            assert match.skill_name == "test_skill"
            print(f"Match wrapper found: {match.skill_name}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retrieve_wrapper():
    """Test retrieve() wrapper for backward compatibility.

    This test does not need VCR as it only tests namespace retrieval.
    """
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()
    mock_skills = [
        MagicMock(spec=LearnedSkill, namespace="test/ns"),
    ]

    # Use unique query to avoid cache collisions
    import uuid
    unique_query = f"test/ns query {uuid.uuid4().hex[:8]}"

    with patch.object(SkillDiscovery, '_get_skills_by_namespace', new_callable=lambda: AsyncMock(return_value=mock_skills)):
        with patch.object(SkillDiscovery, '_get_active_skills', new_callable=lambda: AsyncMock(return_value=mock_skills)):
            _, skills, _ = await discovery.exact_search(unique_query, namespace_context="test/ns")

            assert len(skills) == 1
