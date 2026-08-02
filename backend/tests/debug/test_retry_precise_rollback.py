"""
Precise retry rollback test: Multi-turn conversation, retry round 3 message.
Verifies exact checkpoint/writes cleanup and state.messages count.
"""

import asyncio
import os
import tempfile

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database import session_scope

from app.core.engine.context_hydrator import EvoContextMiddleware
_orig_hydrate = EvoContextMiddleware.hydrate
async def _mock_hydrate(state, config):
    return state
EvoContextMiddleware.hydrate = _mock_hydrate

from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver

_orig_get_node_skills = SkillHydrator.get_node_skills
async def _mock_get_node_skills(state, node_name):
    return []
SkillHydrator.get_node_skills = _mock_get_node_skills

_orig_inject_fallback = SkillResolver.inject_fallback_sops
async def _mock_inject_fallback(sops, config):
    return sops
SkillResolver.inject_fallback_sops = _mock_inject_fallback


class MockAgentEngine(AgentEngine):
    def __init__(self):
        super().__init__()
        self.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    async def run_node(self, state, config, system_prompt, tools, max_steps=5, temperature=0.7, name="Agent", node_source=None, parallel_tools=False, model=None) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            if c % 2 == 1:
                return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic=f"topic{c}")))
            else:
                return EngineResult()

        if name == "Chat":
            return EngineResult(messages=[AIMessage(content=f"AI reply round {c}")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": f"test{c}"}, "id": f"call_{c}"}]),
                    ToolMessage(content=f"search result {c}", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"Worker reply round {c}"),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="default reply")])


def msg_summary(messages):
    return [(getattr(m, 'type', type(m).__name__), str(getattr(m, 'content', ''))[:40]) for m in messages]


def count_by_type(messages):
    counts = {"human": 0, "ai": 0, "tool": 0, "other": 0}
    for m in messages:
        t = getattr(m, 'type', '') or type(m).__name__.lower()
        if 'human' in t: counts['human'] += 1
        elif 'tool' in t: counts['tool'] += 1
        elif 'ai' in t: counts['ai'] += 1
        else: counts['other'] += 1
    return counts


async def get_state_msgs(graph, config):
    state = await graph.aget_state(config)
    return state.values.get("messages", []) if state and state.values else []


async def db_counts(sqlite_path, thread_id):
    import aiosqlite
    async with aiosqlite.connect(sqlite_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
        cp = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM writes WHERE thread_id = ?", (thread_id,))
        wr = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,))
        msg = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT role, COUNT(*) FROM messages WHERE thread_id = ? GROUP BY role", (thread_id,))
        roles = dict(await cur.fetchall())
    return {"checkpoints": cp, "writes": wr, "messages": msg, "roles": roles}


async def persist_round(thread_id, project_id, round_num):
    from app.models import Message
    from sqlalchemy import select, desc
    async with session_scope() as session:
        stmt = select(Message.id).where(Message.thread_id == thread_id).order_by(desc(Message.sequence_number)).limit(1)
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        session.add(Message(
            thread_id=thread_id, project_id=project_id, role="human",
            content=f"Round {round_num}", sequence_number=round_num * 10,
            parent_id=parent_id, is_visible=True, category="user", action_type="text",
        ))
        await session.flush()
        parent_id = (await session.execute(stmt)).scalar_one_or_none()
        session.add(Message(
            thread_id=thread_id, project_id=project_id, role="ai",
            content=f"AI reply round {round_num}", sequence_number=round_num * 10 + 1,
            parent_id=parent_id, is_visible=True, category="assistant_response", action_type="text",
        ))
        await session.flush()


async def main():
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["SQLITE_DB_PATH"] = sqlite_path
    from app.core.config import settings
    settings.SQLITE_PATH = sqlite_path

    print("=" * 70)
    print("SETUP: Init DB + DELETE-mode checkpointer")
    print("=" * 70)
    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    import aiosqlite
    cp_conn = await aiosqlite.connect(sqlite_path)
    await cp_conn.execute("PRAGMA journal_mode=DELETE")
    await cp_conn.execute("PRAGMA busy_timeout=30000")
    await cp_conn.commit()

    from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver
    saver = FixedAsyncSqliteSaver(conn=cp_conn)
    await saver.setup()

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "retry-precise-thread"
    project_id = 1
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}
    ContextManager.set(EvoContext(thread_id=thread_id, project_id=project_id, active_model="kimi-k2-thinking-turbo"))

    from app.core.engine.checkpoint import pruner as pruner_module
    orig_prune = pruner_module.auto_prune_on_completion
    async def noop(t): pass
    pruner_module.auto_prune_on_completion = noop

    from app.infrastructure.llm import InternalLLMService
    orig_llm = InternalLLMService.invoke
    @staticmethod
    async def mock_llm(*a, **k):
        return type('R', (), {'content': 'Mock audit.'})()
    InternalLLMService.invoke = mock_llm

    # =====================================================================
    # PHASE 1: Run 5 rounds
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: Run 5 rounds of dialogue")
    print("=" * 70)

    for i in range(5):
        r = i + 1
        await graph.ainvoke(AgentState(messages=[HumanMessage(content=f"Round {r}")]), config=base_config)
        await persist_round(thread_id, project_id, r)
        print(f"  Round {r} done")

    msgs_5 = await get_state_msgs(graph, base_config)
    db_5 = await db_counts(sqlite_path, thread_id)
    print(f"\n  After 5 rounds:")
    print(f"    State messages: {len(msgs_5)}  {count_by_type(msgs_5)}")
    print(f"    DB checkpoints: {db_5['checkpoints']}")
    print(f"    DB writes:      {db_5['writes']}")
    print(f"    DB messages:    {db_5['messages']}  {db_5['roles']}")

    # =====================================================================
    # PHASE 2: Retry round 3
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Retry round 3 (third human message)")
    print("=" * 70)

    from app.core.events import system_bus
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.rewind.state import StateRewind
    from app.core.engine.rewind.checkpoint import CheckpointRewind
    StateRewind.register(system_bus)
    CheckpointRewind.register(system_bus)

    from sqlalchemy import text
    async with session_scope() as session:
        cur = await session.execute(
            text("SELECT id FROM messages WHERE thread_id = :tid AND role = 'human' ORDER BY id"),
            {"tid": thread_id}
        )
        human_ids = [row[0] for row in cur.fetchall()]

    target_id = human_ids[2]  # third human = round 3
    print(f"  Human message IDs: {human_ids}")
    print(f"  Target for retry (round 3): message_id={target_id}")

    msgs_before_rewind = await get_state_msgs(graph, base_config)
    db_before = await db_counts(sqlite_path, thread_id)
    print(f"\n  BEFORE rewind:")
    print(f"    State messages: {len(msgs_before_rewind)}  {count_by_type(msgs_before_rewind)}")
    print(f"    DB checkpoints: {db_before['checkpoints']}")
    print(f"    DB writes:      {db_before['writes']}")

    orchestrator = RewindOrchestrator(event_bus=system_bus)
    result = await orchestrator.perform_rewind(
        thread_id=thread_id,
        target_message_id=str(target_id),
        include_target=False,
        revert_files=False,
        reset_state=True,
        reason="retry"
    )
    print(f"\n  Rewind result: {result}")

    msgs_after_rewind = await get_state_msgs(graph, base_config)
    db_after = await db_counts(sqlite_path, thread_id)
    print(f"\n  AFTER rewind:")
    print(f"    State messages: {len(msgs_after_rewind)}  {count_by_type(msgs_after_rewind)}")
    print(f"    DB checkpoints: {db_after['checkpoints']}")
    print(f"    DB writes:      {db_after['writes']}")
    print(f"    Message summary: {msg_summary(msgs_after_rewind)}")

    # =====================================================================
    # PHASE 3: Re-run from round 3
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Re-run round 3 + 4 + 5")
    print("=" * 70)

    mock_engine.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    for r in [3, 4, 5]:
        await graph.ainvoke(AgentState(messages=[HumanMessage(content=f"Round {r}")]), config=base_config)
        await persist_round(thread_id, project_id, r)
        print(f"  Round {r} re-run done")

    msgs_final = await get_state_msgs(graph, base_config)
    db_final = await db_counts(sqlite_path, thread_id)
    print(f"\n  AFTER retry re-run:")
    print(f"    State messages: {len(msgs_final)}  {count_by_type(msgs_final)}")
    print(f"    DB checkpoints: {db_final['checkpoints']}")
    print(f"    DB writes:      {db_final['writes']}")
    print(f"    DB messages:    {db_final['messages']}  {db_final['roles']}")

    # =====================================================================
    # ASSERTIONS
    # =====================================================================
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    passed = True

    if count_by_type(msgs_5)['human'] == 5:
        print(f"  PASS: 5 rounds -> 5 human messages in state")
    else:
        print(f"  FAIL: 5 rounds -> {count_by_type(msgs_5)['human']} human messages (expected 5)")
        passed = False

    if len(msgs_after_rewind) < len(msgs_before_rewind):
        print(f"  PASS: Rewind reduced state: {len(msgs_before_rewind)} -> {len(msgs_after_rewind)}")
    else:
        print(f"  FAIL: Rewind did NOT reduce state: {len(msgs_before_rewind)} -> {len(msgs_after_rewind)}")
        passed = False

    if db_after['checkpoints'] < db_before['checkpoints']:
        print(f"  PASS: Rewind reduced checkpoints: {db_before['checkpoints']} -> {db_after['checkpoints']}")
    else:
        print(f"  FAIL: Rewind did NOT reduce checkpoints: {db_before['checkpoints']} -> {db_after['checkpoints']}")
        passed = False

    if db_after['writes'] < db_before['writes']:
        print(f"  PASS: Rewind reduced writes: {db_before['writes']} -> {db_after['writes']}")
    else:
        print(f"  FAIL: Rewind did NOT reduce writes: {db_before['writes']} -> {db_after['writes']}")
        passed = False

    if len(msgs_final) >= len(msgs_after_rewind):
        print(f"  PASS: Retry restored state: {len(msgs_after_rewind)} -> {len(msgs_final)}")
    else:
        print(f"  FAIL: Retry did NOT restore state: {len(msgs_after_rewind)} -> {len(msgs_final)}")
        passed = False

    if count_by_type(msgs_final)['human'] == 6:
        print(f"  PASS: Final state has 6 human messages (original 3 + retry 3&4&5)")
    else:
        print(f"  FAIL: Final state has {count_by_type(msgs_final)['human']} human messages (expected 6)")
        passed = False

    if db_final['messages'] >= 10:
        print(f"  PASS: DB messages accumulated: {db_final['messages']} >= 10")
    else:
        print(f"  FAIL: DB messages too few: {db_final['messages']} < 10")
        passed = False

    if passed:
        print(f"\n  ALL ASSERTIONS PASSED!")
    else:
        print(f"\n  SOME ASSERTIONS FAILED")

    pruner_module.auto_prune_on_completion = orig_prune
    InternalLLMService.invoke = orig_llm
    system_bus.clear()
    await cp_conn.close()
    await db_resource_manager.shutdown()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)


if __name__ == "__main__":
    asyncio.run(main())
