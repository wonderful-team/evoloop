"""Unit tests for skill slug lookup and webfetch local file guidance."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.learning.skills.discovery import SkillDiscovery
from app.core.engine.tools.react_webfetch import webfetch


class TestSkillSlugLookup:
    @pytest.mark.asyncio
    async def test_slug_and_case_insensitive_matching(self):
        discovery = SkillDiscovery()
        skill_reach = SimpleNamespace(
            id=44,
            name="Agent Reach",
            is_active=True,
            status="verified",
            resource_path="/Users/test/.evoloop/skills/agent-reach",
        )
        skill_other = SimpleNamespace(
            id=45,
            name="Data Analysis Pro",
            is_active=True,
            status="verified",
            resource_path="/Users/test/.evoloop/skills/data-analysis-pro",
        )

        with patch.object(discovery, "_get_active_skills", AsyncMock(return_value=[skill_reach, skill_other])):
            discovery._id_map = {skill_reach.id: skill_reach, skill_other.id: skill_other}
            # Populate name_map using the new logic
            name_map = {}
            for s in [skill_reach, skill_other]:
                name_map[s.name.lower()] = s
                norm = s.name.lower().replace("-", " ").replace("_", " ")
                name_map[norm] = s
                slug = "-".join(norm.split())
                name_map[slug] = s
                if getattr(s, "resource_path", None):
                    import os
                    base_name = os.path.basename(os.path.normpath(s.resource_path)).lower()
                    if base_name:
                        name_map[base_name] = s
            discovery._name_map = name_map

            # Test exact name
            m1, rel1, _ = await discovery.exact_search("Agent Reach")
            assert m1 is not None and rel1[0].name == "Agent Reach"

            # Test hyphenated slug (this was the failure point!)
            m2, rel2, _ = await discovery.exact_search("agent-reach")
            assert m2 is not None and rel2[0].name == "Agent Reach"

            # Test underscore slug
            m3, rel3, _ = await discovery.exact_search("agent_reach")
            assert m3 is not None and rel3[0].name == "Agent Reach"

            # Test uppercase hyphen
            m4, rel4, _ = await discovery.exact_search("AGENT-REACH")
            assert m4 is not None and rel4[0].name == "Agent Reach"

            # Test another skill
            m5, rel5, _ = await discovery.exact_search("data-analysis-pro")
            assert m5 is not None and rel5[0].name == "Data Analysis Pro"


class TestWebFetchGuidance:
    @pytest.mark.asyncio
    async def test_file_url_guides_to_read_tool(self):
        res = await webfetch("file:///Users/test/social.md")
        assert "use the `read` tool" in res
        assert "/Users/test/social.md" in res

    @pytest.mark.asyncio
    async def test_local_path_guides_to_read_tool(self):
        res = await webfetch("/Users/test/social.md")
        assert "use the `read` tool" in res
