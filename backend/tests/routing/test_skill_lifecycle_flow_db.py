"""Full skill lifecycle against a real SQLite DB (audit of mock-heavy tests).

Unlike tests/unit/core/learning/test_skill_lifecycle_current.py, this file does
NOT patch session_scope: the route handlers, the confirmation endpoint, the
route-index sync and upsert all read/write a real database. Only true external
boundaries are stubbed (event publisher, skill discovery, embedder, YAML parse).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.learning import skills as skill_routes
from app.core.learning.schemas.requests import CreateSkillFromYamlRequest
from app.core.routing import sync
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill


def _discovery_stub():
    stub = MagicMock()
    stub.reload = AsyncMock()
    stub.ensure_system_skills_synced = AsyncMock()
    return stub


@pytest.mark.asyncio
async def test_full_skill_lifecycle_against_real_db(_real_db, monkeypatch):
    # 1. Create via the real HTTP handler -> real DB row.
    with (
        patch(
            "app.api.routes.learning.skills.validate_macro_yaml",
            return_value=(True, []),
        ),
        patch(
            "app.api.routes.learning.skills.macro_from_yaml",
            return_value=[{"tool": "noop"}],
        ),
        patch(
            "app.api.routes.learning.skills.publish_skill_mutated",
            new_callable=AsyncMock,
        ),
        patch("app.api.routes.learning.skills.skill_discovery", _discovery_stub()),
    ):
        created = await skill_routes.create_skill_from_yaml(
            CreateSkillFromYamlRequest(name="flow_skill", yaml_content="steps: []"),
            MagicMock(),
            current_user=SimpleNamespace(id=0),
        )

    assert created.success is True
    skill_id = created.skill_id

    # 2. Real DB row must be pending_review + inactive.
    async with session_scope() as db:
        row = await db.get(LearnedSkill, skill_id)
    assert row is not None
    assert row.status == "pending_review"
    assert row.is_active is False

    # 3. Real route-index sync (real DB) must exclude the unconfirmed skill.
    assert f"skill:{skill_id}" not in {e["id"] for e in sync._skill_entries()}

    # 4. Confirm via the real handler -> verified + active in the real DB.
    with patch(
        "app.api.routes.learning.skills.publish_skill_mutated", new_callable=AsyncMock
    ):
        confirmed = await skill_routes.confirm_learned_skill(
            skill_id, current_user=SimpleNamespace(id=0)
        )
    assert confirmed.success is True

    async with session_scope() as db:
        row = await db.get(LearnedSkill, skill_id)
    assert row.status == "verified"
    assert row.is_active is True

    # 5. Now the real sync includes it; string params parse into a schema.
    entries = {e["id"]: e for e in sync._skill_entries()}
    assert f"skill:{skill_id}" in entries
    assert entries[f"skill:{skill_id}"]["params_schema"] == {}

    # 6. upsert_skill against the real DB writes the entry into the index.
    index = MagicMock()
    index.upsert.return_value = 1
    monkeypatch.setattr(sync, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(sync, "get_index", lambda: index)
    assert await sync.upsert_skill(skill_id) is True
    written = index.upsert.call_args[0][0]
    assert written[0]["id"] == f"skill:{skill_id}"

    # 7. Listing (active_only default) returns the confirmed skill.
    with patch("app.api.routes.learning.skills.skill_discovery", _discovery_stub()):
        listing = await skill_routes.list_skills(
            page=1, page_size=50, current_user=SimpleNamespace(id=0)
        )
    ids = [s.id for s in listing.data]
    assert skill_id in ids
    listed = next(s for s in listing.data if s.id == skill_id)
    assert listed.status == "verified"
    assert listed.is_active is True


@pytest.mark.asyncio
async def test_confirm_is_required_for_routing_against_real_db(_real_db):
    # Create two skills directly in the real DB: one confirmed, one not.
    async with session_scope() as db:
        pending = LearnedSkill(
            member_id=0,
            name="pending_flow",
            description="",
            trigger_patterns=json.dumps(["x"]),
            parameters=json.dumps([]),
            status="pending_review",
            is_active=True,
        )
        verified = LearnedSkill(
            member_id=0,
            name="verified_flow",
            description="",
            trigger_patterns=json.dumps(["y"]),
            parameters=json.dumps([]),
            status="verified",
            is_active=True,
        )
        db.add(pending)
        db.add(verified)
        await db.flush()
        pending_id = pending.id
        verified_id = verified.id

    # Only the confirmed skill may enter the route index; pending_review stays
    # out even though is_active=True (status gate, ROUTE_INDEX_REQUIRE_VERIFIED).
    ids = {e["id"] for e in sync._skill_entries()}
    assert f"skill:{pending_id}" not in ids
    assert f"skill:{verified_id}" in ids


class _FakeEmbedder:
    async def embed_query(self, _text: str) -> list[float]:
        return [0.1] * 8
