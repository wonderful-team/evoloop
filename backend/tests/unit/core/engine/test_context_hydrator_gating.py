"""层 A 全链路：AgentContextHydrator.hydrate() 的 intent 门控 → active_skills。

复现自 /tmp/repro_skill_visibility.py（2026-09 复现）+ hydrate 真实链路：
- intent ∈ {direct_answer, memory_query, environment_query} → 索引整块缺席
  （context_hydrator._INTENTS_NEEDING_ACTIVE_SKILLS 门控 → _load_active_skills 返回 ""）
- intent ∈ {worker_task, macro_task, ambiguous} / None → skill_discovery 全量加载
- explicit_skills 是无视门控的精确旁路（前端勾选场景）
- 域分类路径：domain_classified 经 profile-first/默认映射解析为 worker_task → 加载

边界 mock 仅为 memory 容器（Tier1/2 记忆管线是独立关注点，测试断言不涉及其内容）；
其余全链路为真实组件：hook_system、LayeredContextCache、skill_discovery（真实
sqlite）、macro 索引、包预选（preselection）、插件水合、context polishing 事件。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.context.manager import EvoContext
from app.core.engine.context_hydrator import AgentContextHydrator
from app.core.routing.constants import (
    INTENT_DIRECT_ANSWER,
    INTENT_DOMAIN_CLASSIFIED,
    INTENT_ENVIRONMENT_QUERY,
    INTENT_MEMORY_QUERY,
    INTENT_WORKER_TASK,
)
from tests.unit.db_stub import stub_db_for_loop

SEEDED_SKILLS = ("alpha-reach", "beta-research", "gamma-wiki")


@pytest.fixture
async def _hydrator_db(monkeypatch):
    """In-memory sqlite + 全表，注册进 db_resource_manager（当前 loop）。"""
    from app.infrastructure.database.sql.database import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)
    async with factory() as session:
        await session.run_sync(
            lambda sess: Base.metadata.create_all(sess.get_bind(), checkfirst=True)
        )
    yield factory
    await engine.dispose()


async def _seed_skills(factory) -> None:
    """种子 3 个 verified 技能（真实 ORM 行，经 skill_discovery 真实查询）。"""
    from sqlalchemy import select

    from app.models.learning import LearnedSkill

    async with factory() as session:
        existing = await session.execute(
            select(LearnedSkill).where(LearnedSkill.name.in_(SEEDED_SKILLS))
        )
        if not existing.scalars().all():
            for name in SEEDED_SKILLS:
                session.add(
                    LearnedSkill(
                        name=name,
                        description=f"{name} 的种子描述。",
                        status="verified",
                        is_active=True,
                        namespace="general",
                        skill_source="imported",
                        trigger_patterns=[f"测试触发 {name}"],
                        parameters=[],
                    )
                )
            await session.commit()


@pytest.fixture
async def _skills_ready(_hydrator_db, monkeypatch):
    """种子技能 + 让 skill_discovery 单例读测试 DB（跳过内置技能同步）。"""
    from app.core.learning.skills.discovery import skill_discovery

    await _seed_skills(_hydrator_db)
    # 跳过 ensure_system_skills_synced（会拷贝内置技能到真实 ~/.evoloop，测试禁触碰）
    monkeypatch.setattr(skill_discovery, "_system_skills_synced", True)
    # 单例进程级缓存可能被其他测试填充 → 强制重读
    skill_discovery._skills_cache = None
    skill_discovery._skills_list_cache = None
    await skill_discovery.reload()
    return _hydrator_db


@pytest.fixture
def _memory_stub(monkeypatch):
    """memory 容器边界 mock：Tier1/2 记忆管线返回空，不参与本测试断言。"""
    from app.core.engine.context_hydrator import AgentContextHydrator

    memory_manager = SimpleNamespace(
        get_hot_memory=AsyncMock(return_value=""),
        search_concepts=AsyncMock(return_value=[]),
        search_episodes=AsyncMock(return_value=[]),
    )
    container = SimpleNamespace(memory_manager=memory_manager)

    async def _fake_container():
        return container

    monkeypatch.setattr(
        AgentContextHydrator,
        "_get_shared_memory_container",
        classmethod(lambda cls: _fake_container()),
    )


def _mk_inputs(thread_id: str, hint: dict | None, explicit: list | None = None):
    state = SimpleNamespace(
        session_goal="测试目标",
        shared_context={},
        tool_memory={},
    )
    metadata: dict = {"is_retry": False}
    if hint is not None:
        metadata["intent_hint"] = hint
    if explicit is not None:
        metadata["explicit_skills"] = explicit
    config = {
        "configurable": {"run_id": f"run-{uuid.uuid4().hex[:8]}"},
        "metadata": metadata,
    }
    ctx = EvoContext(
        thread_id=thread_id,
        project_id=1,
        working_directory="/tmp/evoloop-test",
    )
    return ctx, state, config


def _hint(intent: str | None, domain: str | None = None) -> dict | None:
    if intent is None and domain is None:
        return None
    payload: dict = {"intent": intent, "reason": "test"}
    if domain is not None:
        payload["domain"] = domain
    return payload


async def _hydrate(intent=None, domain=None, explicit=None) -> EvoContext:
    thread_id = f"tid-{uuid.uuid4().hex[:12]}"
    ctx, state, config = _mk_inputs(thread_id, _hint(intent, domain), explicit)
    await AgentContextHydrator.hydrate(
        ctx=ctx,
        state=state,
        config=config,
        last_human_msg="测试消息",
        is_retry=False,
        iteration_count=0,
    )
    return ctx


@pytest.mark.usefixtures("_memory_stub")
class TestLayerAIntentGatingFullChain:
    async def test_environment_query_hides_index(self, _skills_ready):
        ctx = await _hydrate(intent=INTENT_ENVIRONMENT_QUERY)
        # LayeredContextCache 将 loader 的 "" 归一为 []；渲染层 if skills: 对
        # 两者都判假 → <available_skills> 块缺席。断言 falsy 语义。
        assert not ctx.metadata.active_skills

    async def test_direct_answer_hides_index(self, _skills_ready):
        ctx = await _hydrate(intent=INTENT_DIRECT_ANSWER)
        assert not ctx.metadata.active_skills

    async def test_memory_query_hides_index(self, _skills_ready):
        ctx = await _hydrate(intent=INTENT_MEMORY_QUERY)
        assert not ctx.metadata.active_skills

    async def test_worker_task_loads_skills_from_db(self, _skills_ready):
        ctx = await _hydrate(intent=INTENT_WORKER_TASK)
        names = [item.name for item in ctx.metadata.active_skills]
        assert set(SEEDED_SKILLS) <= set(names)

    async def test_no_intent_full_load(self, _skills_ready):
        ctx = await _hydrate(intent=None)
        names = [item.name for item in ctx.metadata.active_skills]
        assert set(SEEDED_SKILLS) <= set(names)

    async def test_domain_classified_resolves_to_worker_task(self, _skills_ready):
        """域分类路径：profile-first 解析（无 profile → 默认映射）→ worker_task → 加载。"""
        ctx = await _hydrate(intent=INTENT_DOMAIN_CLASSIFIED, domain="ecommerce")
        names = [item.name for item in ctx.metadata.active_skills]
        assert set(SEEDED_SKILLS) <= set(names)
        # resolved hint 写回 ctx（下游 ToolsManager 从 ctx 读）
        assert ctx.metadata.intent_hint.intent == INTENT_WORKER_TASK

    async def test_explicit_skills_bypass_intent_gate(self, _skills_ready):
        """显式技能精确预载：门控 intent（environment_query）下仍可见指定技能。"""
        ctx = await _hydrate(
            intent=INTENT_ENVIRONMENT_QUERY, explicit=[{"name": "alpha-reach"}]
        )
        names = [item.name for item in ctx.metadata.active_skills]
        assert names == ["alpha-reach"]
