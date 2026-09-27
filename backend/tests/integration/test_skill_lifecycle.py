"""Unit coverage for app.core.learning.skills.lifecycle write helpers.

Runs against a throwaway SQLite DB (see tests/integration/conftest.py).
Lifecycle write functions take the caller's session explicitly, so tests
drive them through ``test_session_scope`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.core.learning.schemas import ValidationResult
from app.core.learning.skills import lifecycle
from app.core.learning.skills.lifecycle import (
    SkillConflictError,
    SkillNotFoundError,
    apply_validation_result,
    confirm_skill,
    delete_skill,
    patch_skill,
    update_skill,
)
from app.models.learning import LearnedSkill


def _skill(name: str, *, member_id: int = 0, is_active: bool = True, status: str = "verified", **kw) -> LearnedSkill:
    defaults = {
        "name": name,
        "description": f"desc {name}",
        "trigger_patterns": [name],
        "parameters": [],
        "member_id": member_id,
        "is_active": is_active,
        "status": status,
    }
    defaults.update(kw)
    return LearnedSkill(**defaults)


@pytest.fixture(autouse=True)
def _clean_skills(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(LearnedSkill))

    asyncio.run(_clean())


@pytest.mark.asyncio
class TestApplyValidationResult:
    async def test_sets_lifecycle_pair_and_report(self):
        skill = _skill("v")
        validation = ValidationResult(
            is_valid=True, status="healthy", errors=[], warnings=[], metadata={"name": "v"}
        )
        await apply_validation_result(skill, validation)
        assert skill.status == "verified"
        assert skill.is_active is True
        assert skill.validation_report == validation.model_dump()

    async def test_warning_status_becomes_candidate(self):
        skill = _skill("w")
        validation = ValidationResult(
            is_valid=True, status="warning", errors=[], warnings=["x"], metadata={}
        )
        await apply_validation_result(skill, validation)
        assert skill.status == "candidate"
        assert skill.is_active is True


@pytest.mark.asyncio
class TestPatchSkill:
    async def test_only_non_none_fields_applied(self):
        skill = _skill("p", instructions="old")
        await patch_skill(
            skill,
            name=None,
            description="new desc",
            namespace="os/x",
            instructions=None,
            parameters=[{"name": "p1"}],
            preconditions=[{"cond": 1}],
            validation_report={"status": "verified"},
            macro_id=3,
            trigger_patterns=["x", "y"],
        )
        assert skill.name == "p"
        assert skill.description == "new desc"
        assert skill.namespace == "os/x"
        assert skill.instructions == "old"
        assert skill.parameters == [{"name": "p1"}]
        assert skill.preconditions == [{"cond": 1}]
        assert skill.validation_report == {"status": "verified"}
        assert skill.macro_id == 3
        assert skill.trigger_patterns == ["x", "y"]

    async def test_clears_via_explicit_none_is_not_supported(self):
        # None is treated as "leave untouched"; setting instructions=None keeps old value
        skill = _skill("p", instructions="keep")
        await patch_skill(skill, instructions=None)
        assert skill.instructions == "keep"


@pytest.mark.asyncio
class TestUpdateSkill:
    async def test_partial_update(self, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("u", member_id=5)
            db.add(s)
            await db.flush()
            sid = s.id
            await update_skill(
                db, sid, 5, name="u2", description="renamed", trigger_patterns=["t"]
            )
            await db.flush()
            assert s.name == "u2" and s.description == "renamed"

    async def test_not_found(self, test_session_scope):
        async with test_session_scope() as db:
            with pytest.raises(SkillNotFoundError):
                await update_skill(db, 999_999, 5, name="x")

    async def test_outside_member_scope(self, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("mine", member_id=5)
            db.add(s)
            await db.flush()
            sid = s.id
            with pytest.raises(SkillNotFoundError):
                await update_skill(db, sid, 99, name="x")

    async def test_name_collision(self, test_session_scope):
        async with test_session_scope() as db:
            a = _skill("a", member_id=5)
            b = _skill("b", member_id=5)
            db.add_all([a, b])
            await db.flush()
            with pytest.raises(SkillConflictError):
                await update_skill(db, b.id, 5, name="a")

    async def test_same_name_skips_collision(self, test_session_scope):
        async with test_session_scope() as db:
            a = _skill("a", member_id=5)
            db.add(a)
            await db.flush()
            updated = await update_skill(db, a.id, 5, name="a")
            assert updated.name == "a"


@pytest.mark.asyncio
class TestConfirmSkill:
    async def test_confirm_pending_review(self, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("c", member_id=5, status="pending_review", is_active=False)
            db.add(s)
            await db.flush()
            sid = s.id
            confirmed = await confirm_skill(db, sid, 5)
            assert confirmed.status == "verified"
            assert confirmed.is_active is True

    async def test_not_found(self, test_session_scope):
        async with test_session_scope() as db:
            with pytest.raises(SkillNotFoundError):
                await confirm_skill(db, 999_999, 5)

    async def test_wrong_status(self, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("c2", member_id=5, status="verified")
            db.add(s)
            await db.flush()
            with pytest.raises(SkillConflictError):
                await confirm_skill(db, s.id, 5)


@pytest.mark.asyncio
class TestDeleteSkill:
    async def test_deletes_row_and_resource_folder(self, test_session_scope, tmp_path: Path):
        resource = tmp_path / "skill_dir"
        resource.mkdir()
        (resource / "SKILL.md").write_text("---\nname: d\n---\n")

        async with test_session_scope() as db:
            s = _skill("d", member_id=5, resource_path=str(resource))
            db.add(s)
            await db.flush()
            sid = s.id
            deleted = await delete_skill(db, sid, 5)
            assert deleted is not None

        assert not resource.exists()
        async with test_session_scope() as db:
            assert await db.get(LearnedSkill, sid) is None

    async def test_not_found(self, test_session_scope):
        async with test_session_scope() as db:
            with pytest.raises(SkillNotFoundError):
                await delete_skill(db, 999_999, 5)


@pytest.mark.asyncio
class TestCreateFromSynthesis:
    async def test_persists_pending_review(self, test_session_scope):
        async with test_session_scope() as db:
            skill = await lifecycle.create_from_synthesis(
                db, name="syn", member_id=3, description="d", trigger_patterns=["t"]
            )
            await db.flush()
            assert skill.id is not None
            assert skill.status == "pending_review"
            assert skill.is_active is False
            assert skill.member_id == 3

    async def test_name_deduplicated(self, test_session_scope):
        async with test_session_scope() as db:
            first = await lifecycle.create_from_synthesis(db, name="dup", member_id=0)
            await db.flush()
            second = await lifecycle.create_from_synthesis(db, name="dup", member_id=0)
            await db.flush()
            assert first.name == "dup"
            assert second.name == "dup_1"
