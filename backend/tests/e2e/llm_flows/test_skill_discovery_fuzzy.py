import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.learning.discovery import SkillDiscovery, SkillMatch
from app.models.learning import LearnedSkill

@pytest.mark.asyncio
async def test_fuzzy_fallback():
    # 1. Setup mock skills
    mock_skill = LearnedSkill(
        id=1,
        name="Browser Navigate",
        description="Standard procedure for navigating to a URL or searching in Chrome/Safari.",
        namespace="browser/mac",
        instructions="Go to URL",
        trigger_patterns="[]"
    )
    
    discovery = SkillDiscovery()
    # Mock exact match to fail
    discovery._match_regex = AsyncMock(return_value=None)
    # Mock namespace to return our mock skill
    discovery._get_skills_by_namespace = AsyncMock(return_value=[mock_skill])
    # Mock _sync_system_skills to do nothing
    discovery._sync_system_skills = AsyncMock()
    
    # 2. Test Fuzzy Match
    # "searching in Chrome" shares keywords with "Standard procedure for navigating to a URL or searching in Chrome/Safari."
    query = "Search for evopedia in Chrome"
    match, relevant = await discovery.exact_search(query, namespace_context="browser/mac")
    
    # 3. Assertions
    assert match is not None, "Fuzzy match should have found a result"
    assert match.skill_name == "Browser Navigate", "Should match the mock skill"
    assert match.confidence == 0.7, "Should have a confidence of 0.7 for fuzzy"
    assert len(relevant) == 1, "Should return the skill in the relevant list"
    
@pytest.mark.asyncio
async def test_zero_sop_fallback():
    discovery = SkillDiscovery()
    discovery._match_regex = AsyncMock(return_value=None)
    # Empty namespace return
    discovery._get_skills_by_namespace = AsyncMock(return_value=[])
    discovery._sync_system_skills = AsyncMock()
    
    match, relevant = await discovery.exact_search("Do something random", namespace_context="os/unknown")
    
    assert match is None, "Should not find any match"
    assert len(relevant) == 0, "Should have no relevant skills"
