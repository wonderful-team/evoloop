"""Tests for the route_to tool allowlist derived from skill requires.tools."""

from __future__ import annotations

import pytest

from app.core.engine.signals.signals import (
    RouteToSignal,
    RoutingContext,
    handle_route_to,
)
from app.core.engine.state import AgentState
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill


@pytest.mark.asyncio
async def test_route_to_derives_tool_allowlist_from_skill(_real_db):
    """handle_route_to reads LearnedSkill.tools_used and sets the ticket allowlist."""
    async with session_scope() as db:
        skill = LearnedSkill(
            name="wiki_test",
            description="Test wiki skill",
            trigger_patterns=["test wiki"],
            parameters=[],
            tools_used=["query_code_chunks", "write_wiki_page"],
            status="verified",
            is_active=True,
        )
        db.add(skill)
        await db.flush()
        skill_id = skill.id

    state = AgentState(messages=[])
    signal = RouteToSignal(
        target="worker",
        reason="test allowlist",
        context=RoutingContext(topic="test"),
        skill_ids=[skill_id],
    )

    update = await handle_route_to(state, signal, {})

    assert update.ticket is not None
    assert update.ticket.agent_config is not None
    assert set(update.ticket.agent_config.tools) == {
        "query_code_chunks",
        "write_wiki_page",
    }


@pytest.mark.asyncio
async def test_route_to_without_skills_has_empty_tool_list(_real_db):
    """Without skill context, agent_config.tools remains empty (fallback to YAML)."""
    state = AgentState(messages=[])
    signal = RouteToSignal(
        target="worker",
        reason="test fallback",
        context=RoutingContext(topic="test"),
    )

    update = await handle_route_to(state, signal, {})

    assert update.ticket is not None
    assert update.ticket.agent_config is not None
    assert update.ticket.agent_config.tools == []
