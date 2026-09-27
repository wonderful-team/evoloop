"""Context hydrator explicit_skills resolution tests.

覆盖 skill_ids 修复：前端勾选/references 附带的 explicit_skills 应精确预加载
进 <available_skills>，而非全量 skill 列表。
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.context_hydrator import _resolve_explicit_skills


def _skill(sid: int, name: str):
    return type(
        "S",
        (),
        {
            "id": sid,
            "name": name,
            "namespace": "doc",
            "description": f"desc {name}",
        },
    )()


@pytest.mark.asyncio
async def test_resolve_by_id():
    skill = _skill(123, "Wiki Generation")
    with patch("app.core.learning.skills.discovery.skill_discovery") as sd:
        sd.get_skill_by_id = AsyncMock(
            side_effect=lambda sid: skill if sid == 123 else None
        )
        sd.exact_search = AsyncMock(
            return_value=(None, [], "No exact match found.")
        )
        out = await _resolve_explicit_skills([{"id": 123, "name": "Wiki Generation"}])
    assert len(out) == 1
    assert out[0]["name"] == "Wiki Generation"
    assert out[0]["namespace"] == "doc"
    assert out[0]["description"] == "desc Wiki Generation"


@pytest.mark.asyncio
async def test_resolve_by_name():
    skill = _skill(456, "Other")
    with patch("app.core.learning.skills.discovery.skill_discovery") as sd:
        sd.get_skill_by_id = AsyncMock(return_value=None)
        sd.exact_search = AsyncMock(return_value=(None, [skill], ""))
        out = await _resolve_explicit_skills([{"name": "Other"}])
    assert len(out) == 1
    assert out[0]["name"] == "Other"


@pytest.mark.asyncio
async def test_skips_missing_skill():
    with patch("app.core.learning.skills.discovery.skill_discovery") as sd:
        sd.get_skill_by_id = AsyncMock(return_value=None)
        sd.exact_search = AsyncMock(return_value=(None, [], ""))
        out = await _resolve_explicit_skills([{"id": 999, "name": "Missing"}])
    assert out == []


@pytest.mark.asyncio
async def test_empty_input_returns_empty():
    with patch("app.core.learning.skills.discovery.skill_discovery"):
        out = await _resolve_explicit_skills([])
    assert out == []


@pytest.mark.asyncio
async def test_ignores_non_dict_items():
    skill = _skill(1, "A")
    with patch("app.core.learning.skills.discovery.skill_discovery") as sd:
        sd.get_skill_by_id = AsyncMock(
            side_effect=lambda sid: skill if sid == 1 else None
        )
        sd.exact_search = AsyncMock(return_value=(None, [], ""))
        out = await _resolve_explicit_skills(["junk", {"id": 1}, None])
    assert len(out) == 1
    assert out[0]["name"] == "A"
