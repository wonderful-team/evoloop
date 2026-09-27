"""Coverage for SkillImporter (filesystem → DB import)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.core.learning.skills import importer as importer_module
from app.core.learning.skills.importer import SkillImporter, _extract_tools_required
from app.models.learning import LearnedSkill

BASE_MD = """---
name: {name}
description: {desc}
---
# Instructions

Do the thing.
"""

CLICK_MD = """---
name: click
description: click a thing
requires:
  tools: [desktop]
---
# Instructions

Click.
"""


@pytest.fixture(autouse=True)
def _clean_skills(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(LearnedSkill))

    asyncio.run(_clean())


@pytest.fixture
def importer_scope(test_session_scope, monkeypatch):
    monkeypatch.setattr(importer_module, "session_scope", test_session_scope)


def _write_skill(folder: Path, content: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "SKILL.md"
    md.write_text(content, encoding="utf-8")
    return md


@pytest.mark.asyncio
class TestImportSingleSkill:
    async def test_imports_new_skill(self, importer_scope, test_session_scope, tmp_path):
        folder = tmp_path / "os" / "demo"
        _write_skill(folder, BASE_MD.format(name="demo", desc="demo skill"))

        ok = await SkillImporter.import_single_skill(folder, namespace="os")
        assert ok is True

        async with test_session_scope() as db:
            row = (
                await db.execute(select(LearnedSkill).where(LearnedSkill.name == "demo"))
            ).scalar_one()
            assert row.status == "verified"
            assert row.is_active is True
            assert row.namespace == "os"
            assert row.skill_source == "imported"
            assert row.tools_used == []

    async def test_updates_existing_verified(self, importer_scope, test_session_scope, tmp_path):
        folder = tmp_path / "os" / "demo"
        _write_skill(folder, BASE_MD.format(name="demo", desc="updated desc"))

        async with test_session_scope() as db:
            db.add(
                LearnedSkill(
                    name="demo",
                    description="old desc",
                    trigger_patterns=["demo"],
                    parameters=[],
                    status="verified",
                    is_active=True,
                )
            )
            await db.flush()

        await SkillImporter.import_single_skill(folder, namespace="os")
        async with test_session_scope() as db:
            row = (
                await db.execute(select(LearnedSkill).where(LearnedSkill.name == "demo"))
            ).scalar_one()
            assert row.description == "updated desc"
            assert row.status == "verified"
            assert row.resource_path == str(folder.absolute())

    async def test_pending_review_skipped(self, importer_scope, test_session_scope, tmp_path):
        folder = tmp_path / "s"
        _write_skill(folder, BASE_MD.format(name="pr", desc="pending"))

        async with test_session_scope() as db:
            db.add(
                LearnedSkill(
                    name="pr",
                    description="orig",
                    trigger_patterns=[],
                    parameters=[],
                    status="pending_review",
                    is_active=False,
                )
            )
            await db.flush()

        await SkillImporter.import_single_skill(folder)
        async with test_session_scope() as db:
            row = (
                await db.execute(select(LearnedSkill).where(LearnedSkill.name == "pr"))
            ).scalar_one()
            assert row.status == "pending_review"
            assert row.description == "orig"

    async def test_invalid_skill_rejected(self, importer_scope, tmp_path):
        folder = tmp_path / "bad"
        folder.mkdir()
        (folder / "SKILL.md").write_text("no frontmatter\n", encoding="utf-8")
        ok = await SkillImporter.import_single_skill(folder)
        assert ok is False


@pytest.mark.asyncio
class TestImportFromDirectory:
    async def test_imports_tree_with_namespace(self, importer_scope, test_session_scope, tmp_path):
        root = tmp_path / "skills"
        (root / "os" / "macos" / "click").mkdir(parents=True)
        (root / "os" / "macos" / "click" / "SKILL.md").write_text(CLICK_MD)
        (root / "misc").mkdir(parents=True)
        (root / "misc" / "SKILL.md").write_text(
            BASE_MD.format(name="root-skill", desc="at root")
        )

        results = await SkillImporter.import_from_directory(str(root))
        assert results["total_found"] == 2
        assert results["imported"] == 2

        async with test_session_scope() as db:
            rows = (await db.execute(select(LearnedSkill))).scalars().all()
            by_name = {r.name: r for r in rows}
            assert by_name["click"].namespace == "os/macos"
            assert by_name["root-skill"].namespace == "misc"
            assert by_name["click"].tools_used == ["desktop"]

    async def test_missing_directory(self, importer_scope, tmp_path):
        results = await SkillImporter.import_from_directory(str(tmp_path / "nope"))
        assert results["total_found"] == 0
        assert len(results["errors"]) == 1

    async def test_skips_invalid(self, importer_scope, test_session_scope, tmp_path):
        root = tmp_path / "skills"
        (root / "good").mkdir(parents=True)
        (root / "good" / "SKILL.md").write_text(BASE_MD.format(name="good", desc="g"))
        (root / "bad").mkdir(parents=True)
        (root / "bad" / "SKILL.md").write_text("no frontmatter\n")

        results = await SkillImporter.import_from_directory(str(root))
        assert results["imported"] == 1
        assert results["skipped"] == 1


class TestExtractToolsRequired:
    def test_list(self):
        assert _extract_tools_required({"requires": {"tools": ["a", "b"]}}) == ["a", "b"]

    def test_string(self):
        assert _extract_tools_required({"requires": {"tools": "solo"}}) == ["solo"]

    def test_missing(self):
        assert _extract_tools_required({"requires": {}}) == []
        assert _extract_tools_required({}) == []
