"""React skill loader unit tests — deterministic skill resolution by name."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.react.skills.manager import MAX_SKILL_FILES, resolve_skill


def _skill(name="greet", resource_path=None):
    return SimpleNamespace(
        name=name,
        description="打招呼",
        instructions="step1\nstep2\n",
        resource_path=resource_path,
    )


@pytest.mark.asyncio
async def test_resolve_skill_returns_none_when_no_match():
    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(None, [], "not found")),
    ):
        assert await resolve_skill("greet") is None


@pytest.mark.asyncio
async def test_resolve_skill_returns_none_when_relevant_empty():
    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(_skill(), [], "match but empty")),
    ):
        assert await resolve_skill("greet") is None


@pytest.mark.asyncio
async def test_resolve_skill_builds_content_and_lists_files(tmp_path):
    resource = tmp_path / "greet"
    resource.mkdir()
    (resource / "template.py").write_text("print('hi')", encoding="utf-8")
    (resource / "notes.md").write_text("notes", encoding="utf-8")
    (resource / "SKILL.md").write_text("meta", encoding="utf-8")
    (resource / "Readme.MD").write_text("readme", encoding="utf-8")
    (resource / "run.sh").write_text("#!/bin/sh", encoding="utf-8")

    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(_skill(resource_path=str(resource)), [_skill(resource_path=str(resource))], "ok")),
    ):
        result = await resolve_skill("greet")

    assert result is not None
    assert result["name"] == "greet"
    assert result["content"] == "# Skill: greet\n\n打招呼\n\nstep1\nstep2\n"
    assert result["base_dir"] == str(resource)
    # SKILL.md 排除，其余按名排序
    assert result["files"] == [
        "Readme.MD",
        "notes.md",
        "run.sh",
        "template.py",
    ]


@pytest.mark.asyncio
async def test_resolve_skill_caps_resource_files(tmp_path):
    resource = tmp_path / "big"
    resource.mkdir()
    for i in range(20):
        (resource / f"f{i}.txt").write_text("x", encoding="utf-8")

    skill = _skill("big", str(resource))
    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(skill, [skill], "ok")),
    ):
        result = await resolve_skill("big")

    assert len(result["files"]) == MAX_SKILL_FILES


@pytest.mark.asyncio
async def test_resolve_skill_invalid_resource_path_yields_no_files():
    skill = _skill("greet", str(Path("/nonexistent/dir")))
    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(skill, [skill], "ok")),
    ):
        result = await resolve_skill("greet")
    assert result["files"] == []
    assert result["content"].startswith("# Skill: greet")


@pytest.mark.asyncio
async def test_resolve_skill_listdir_oserror_is_tolerated(tmp_path, monkeypatch):
    skill = _skill("greet", str(tmp_path))

    def _raise(_path):
        raise OSError("perm denied")

    monkeypatch.setattr("os.path.isdir", lambda _p: True)
    monkeypatch.setattr("os.listdir", _raise)
    with patch(
        "app.core.learning.skills.discovery.skill_discovery.exact_search",
        AsyncMock(return_value=(skill, [skill], "ok")),
    ):
        result = await resolve_skill("greet")

    assert result["files"] == []
    assert result["content"].startswith("# Skill: greet")
