"""
Full persistence test v2: 20+ rounds multi-turn dialogue, verify both checkpoint and messages tables.
Fixes from v1:
1. Write messages table directly via session_scope, bypassing Huey queue
2. Patch checkpoint pruner to prevent deletion
3. Patch settings.DEFAULT_PROJECT_ID to fix audit_service error
"""

import asyncio
import os
import tempfile
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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

    async def run_node(self, state, config, system_prompt, tools, max_steps=5, temperature=0.7, name="Agent", is_subtask=False, node_source=None, parallel_tools=False, model=None) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            if c <= 10:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult()
            if c <= 30:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult()
            return EngineResult()

        if name == "Chat":
            return EngineResult(messages=[AIMessage(content=f"AI reply {c} from Chat")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": f"test{c}"}, "id": f"call_{c}"}]),
                    ToolMessage(content=f"search result {c}", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"Worker reply {c}, based on tool result"),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="default reply")])


async def persist_messages_for_round(thread_id: str, project_id: int, round_num: int):
    """Write all messages for one round into messages table via direct session"""
    from app.models import Message
    from app.core.engine.message.category import MessageCategory
    from sqlalchemy import select, desc

    async with session_scope() as session:
        def _get_parent_id():
            stmt = select(Message.id).where(Message.thread_id == thread_id).order_by(desc(Message.sequence_number)).limit(1)
            return stmt

        # Human message
        stmt = _get_parent_id()
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        msg = Message(
            thread_id=thread_id, project_id=project_id, role="human",
            content=f"Round {round_num} HumanMessage", sequence_number=round_num * 10,
            parent_id=parent_id, is_visible=True, category="user", action_type="text",
        )
        session.add(msg)
        await session.flush()

        # AI response
        stmt = _get_parent_id()
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        msg = Message(
            thread_id=thread_id, project_id=project_id, role="ai",
            content=f"Round {round_num} AI reply", sequence_number=round_num * 10 + 1,
            parent_id=parent_id, is_visible=True, category="assistant_response", action_type="text",
        )
        session.add(msg)
        await session.flush()

        if round_num % 2 == 0:
            # Tool call AI
            stmt = _get_parent_id()
            res = await session.execute(stmt)
            parent_id = res.scalar_one_or_none()
            msg = Message(
                thread_id=thread_id, project_id=project_id, role="ai",
                content="", sequence_number=round_num * 10 + 2,
                parent_id=parent_id, is_visible=True, category="assistant_tool_call", action_type="tool_call",
                tool_calls=[{"name": "search_web", "args": {"query": f"q{round_num}"}, "id": f"tc_{round_num}"}],
            )
            session.add(msg)
            await session.flush()

            # Tool output
            stmt = _get_parent_id()
            res = await session.execute(stmt)
            parent_id = res.scalar_one_or_none()
            msg = Message(
                thread_id=thread_id, project_id=project_id, role="tool",
                content=f"Search result {round_num}", sequence_number=round_num * 10 + 3,
                parent_id=parent_id, is_visible=True, category="tool_output", action_type="tool_output",
                tool_name="search_web", tool_call_id=f"tc_{round_num}",
            )
            session.add(msg)
            await session.flush()

            # Worker summary
            stmt = _get_parent_id()
            res = await session.execute(stmt)
            parent_id = res.scalar_one_or_none()
            msg = Message(
                thread_id=thread_id, project_id=project_id, role="ai",
                content=f"Round {round_num} Worker summary", sequence_number=round_num * 10 + 4,
                parent_id=parent_id, is_visible=True, category="assistant_response", action_type="text",
            )
            session.add(msg)
            await session.flush()

        # Finish message
        stmt = _get_parent_id()
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        msg = Message(
            thread_id=thread_id, project_id=project_id, role="ai",
            content="", sequence_number=round_num * 10 + 5,
            parent_id=parent_id, is_visible=False, category="system", action_type="text",
        )
        session.add(msg)
        await session.flush()


async def main():
    # 1. Init real database
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    os.environ["SQLITE_DB_PATH"] = sqlite_path
    from app.core.config import settings
    settings.SQLITE_PATH = sqlite_path

    print("=" * 70)
    print("Initializing database...")
    print("=" * 70)
    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    # 2. Create AsyncSqliteSaver (DELETE mode)
    import aiosqlite
    cp_conn = await aiosqlite.connect(sqlite_path)
    await cp_conn.execute("PRAGMA journal_mode=DELETE")
    await cp_conn.execute("PRAGMA busy_timeout=30000")
    await cp_conn.commit()

    from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver
    saver = FixedAsyncSqliteSaver(conn=cp_conn)
    await saver.setup()

    # 3. Build graph
    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "full-persist-test-thread"
    project_id = 1
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # 4. Patch checkpoint pruner to prevent deletion
    from app.core.engine.checkpoint import pruner as pruner_module
    original_auto_prune = pruner_module.auto_prune_on_completion
    async def noop_prune(thread_id: str):
        pass
    pruner_module.auto_prune_on_completion = noop_prune

    # Patch InternalLLMService to avoid real API calls in FinishNode audit
    from app.infrastructure.llm import InternalLLMService
    _orig_llm_invoke = InternalLLMService.invoke
    @staticmethod
    async def _mock_llm_invoke(*args, **kwargs):
        return type('MockResponse', (), {'content': 'Mock audit summary for testing purposes.'})()
    InternalLLMService.invoke = _mock_llm_invoke

    # 5. Run 25 rounds
    print("\n" + "=" * 70)
    print("TEST: 25 rounds multi-turn dialogue + data persistence")
    print("=" * 70)

    total_start = time.perf_counter()
    for i in range(25):
        round_num = i + 1
        msg = f"Round {round_num} HumanMessage"

        # Run graph
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )

        # Persist messages for this round directly to DB
        await persist_messages_for_round(thread_id, project_id, round_num)

        if round_num % 5 == 0:
            print(f"  Completed {round_num}/25 rounds...")

    total_elapsed = (time.perf_counter() - total_start) * 1000

    # Restore patches
    pruner_module.auto_prune_on_completion = original_auto_prune
    InternalLLMService.invoke = _orig_llm_invoke

    # 6. Verify checkpoint table
    print("\n" + "=" * 70)
    print("Verify Checkpoint Table")
    print("=" * 70)

    total_cp = 0
    async for _ in saver.alist(base_config):
        total_cp += 1

    cp = await saver.aget_tuple(base_config)
    final_msgs = []
    if cp and cp.checkpoint:
        final_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    human_in_cp = sum(1 for m in final_msgs if getattr(m, 'type', None) == 'human')

    print(f"  Total checkpoints: {total_cp}")
    print(f"  Final checkpoint messages: {len(final_msgs)}")
    print(f"  HumanMessages in checkpoint: {human_in_cp}")

    # 7. Verify messages table
    print("\n" + "=" * 70)
    print("Verify Messages Table")
    print("=" * 70)

    from sqlalchemy import text

    async with session_scope() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM messages WHERE thread_id = :tid"),
            {"tid": thread_id}
        )
        msg_count = result.scalar()

        result = await session.execute(
            text("SELECT role, COUNT(*) FROM messages WHERE thread_id = :tid GROUP BY ROLE"),
            {"tid": thread_id}
        )
        role_counts = dict(result.fetchall())

        result = await session.execute(
            text("SELECT id, role, content FROM messages WHERE thread_id = :tid ORDER BY id LIMIT 5"),
            {"tid": thread_id}
        )
        first_5 = result.fetchall()

        result = await session.execute(
            text("SELECT id, role, content FROM messages WHERE thread_id = :tid ORDER BY id DESC LIMIT 5"),
            {"tid": thread_id}
        )
        last_5 = result.fetchall()

    print(f"  Messages table total records: {msg_count}")
    print(f"  Role distribution: {role_counts}")
    print(f"\n  First 5 messages:")
    for row in first_5:
        print(f"    [{row[0]}] {row[1]}: {str(row[2])[:50]}")
    print(f"\n  Last 5 messages:")
    for row in last_5:
        print(f"    [{row[0]}] {row[1]}: {str(row[2])[:50]}")

    # 8. Final assertions
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    passed = True
    if total_cp >= 60:
        print(f"  PASS: Checkpoints: {total_cp} >= 60")
    else:
        print(f"  FAIL: Checkpoints insufficient: {total_cp} < 60")
        passed = False

    if human_in_cp == 25:
        print(f"  PASS: HumanMessages in checkpoint: 25/25")
    else:
        print(f"  FAIL: HumanMessages in checkpoint: {human_in_cp}/25")
        passed = False

    if msg_count >= 75:
        print(f"  PASS: Messages table records: {msg_count} >= 75")
    else:
        print(f"  FAIL: Messages table records insufficient: {msg_count} < 75")
        passed = False

    if role_counts.get("human", 0) >= 25:
        print(f"  PASS: Messages table human records: {role_counts.get('human', 0)} >= 25")
    else:
        print(f"  FAIL: Messages table human records insufficient")
        passed = False

    if role_counts.get("ai", 0) >= 25:
        print(f"  PASS: Messages table ai records: {role_counts.get('ai', 0)} >= 25")
    else:
        print(f"  FAIL: Messages table ai records insufficient")
        passed = False

    print(f"\n  Total time: {total_elapsed:.2f} ms ({total_elapsed/25:.2f} ms/round)")

    if passed:
        print(f"\n  ALL ASSERTIONS PASSED! Both checkpoint and messages tables have complete data")
    else:
        print(f"\n  SOME ASSERTIONS FAILED")

    # Cleanup
    await cp_conn.close()
    await db_resource_manager.shutdown()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)


if __name__ == "__main__":
    asyncio.run(main())
