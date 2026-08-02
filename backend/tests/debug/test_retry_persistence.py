"""
Retry persistence test: Verify checkpoint and messages behavior during retry/rewind.

Focus: state.messages count changes through retry lifecycle.
"""

import asyncio
import os
import tempfile
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database import session_scope

# Skip DB-dependent hydration
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
            return EngineResult(messages=[AIMessage(content=f"AI reply {c} from Chat")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": f"test{c}"}, "id": f"call_{c}"}]),
                    ToolMessage(content=f"search result {c}", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"Worker reply {c}"),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="default reply")])


def count_messages_by_type(messages):
    """Count message types in a list."""
    counts = {"human": 0, "ai": 0, "tool": 0, "other": 0}
    for m in messages:
        t = getattr(m, 'type', None) or type(m).__name__.lower()
        if t in ('human', 'humanmessage'):
            counts['human'] += 1
        elif t in ('ai', 'aimessage'):
            counts['ai'] += 1
        elif t in ('tool', 'toolmessage'):
            counts['tool'] += 1
        else:
            counts['other'] += 1
    return counts


async def get_current_state_messages(graph, config):
    """Get current state messages from graph."""
    state = await graph.aget_state(config)
    if state and state.values:
        return state.values.get("messages", [])
    return []


async def count_checkpoints(saver, config):
    """Count total checkpoints for a thread."""
    total = 0
    async for _ in saver.alist(config):
        total += 1
    return total


async def persist_messages_for_round(thread_id: str, project_id: int, round_num: int):
    """Write all messages for one round into messages table."""
    from app.models import Message
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


async def main():
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    os.environ["SQLITE_DB_PATH"] = sqlite_path
    from app.core.config import settings
    settings.SQLITE_PATH = sqlite_path

    print("=" * 70)
    print("Initializing database for retry test...")
    print("=" * 70)
    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    # Create AsyncSqliteSaver (DELETE mode)
    import aiosqlite
    cp_conn = await aiosqlite.connect(sqlite_path)
    await cp_conn.execute("PRAGMA journal_mode=DELETE")
    await cp_conn.execute("PRAGMA busy_timeout=30000")
    await cp_conn.commit()

    from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver
    saver = FixedAsyncSqliteSaver(conn=cp_conn)
    await saver.setup()

    # Build graph
    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "retry-test-thread"
    project_id = 1
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # Patch checkpoint pruner and LLM service
    from app.core.engine.checkpoint import pruner as pruner_module
    original_auto_prune = pruner_module.auto_prune_on_completion
    async def noop_prune(thread_id: str):
        pass
    pruner_module.auto_prune_on_completion = noop_prune

    from app.infrastructure.llm import InternalLLMService
    _orig_llm_invoke = InternalLLMService.invoke
    @staticmethod
    async def _mock_llm_invoke(*args, **kwargs):
        return type('MockResponse', (), {'content': 'Mock audit summary.'})()
    InternalLLMService.invoke = _mock_llm_invoke

    # =====================================================================
    # PHASE 1: Run 3 normal rounds
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: Run 3 normal rounds")
    print("=" * 70)

    for i in range(3):
        round_num = i + 1
        msg = f"Round {round_num} HumanMessage"
        await graph.ainvoke(AgentState(messages=[HumanMessage(content=msg)]), config=base_config)
        await persist_messages_for_round(thread_id, project_id, round_num)
        print(f"  Round {round_num} completed")

    # Record state after 3 rounds
    msgs_after_3 = await get_current_state_messages(graph, base_config)
    cp_after_3 = await count_checkpoints(saver, base_config)
    counts_after_3 = count_messages_by_type(msgs_after_3)

    print(f"\n  After 3 rounds:")
    print(f"    Checkpoints: {cp_after_3}")
    print(f"    State messages: {len(msgs_after_3)} (human={counts_after_3['human']}, ai={counts_after_3['ai']}, tool={counts_after_3['tool']})")

    # =====================================================================
    # PHASE 2: Register rewind handlers and perform retry rewind
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Perform retry rewind")
    print("=" * 70)

    from app.core.events import system_bus
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.rewind.state import StateRewind
    from app.core.engine.rewind.checkpoint import CheckpointRewind

    # Register handlers (normally done during app startup)
    StateRewind.register(system_bus)
    CheckpointRewind.register(system_bus)

    # Get the last human message ID from DB for targeting
    from sqlalchemy import text
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT id FROM messages WHERE thread_id = :tid AND role = 'human' ORDER BY id DESC LIMIT 1"),
            {"tid": thread_id}
        )
        last_human_id = result.scalar()

    print(f"  Last human message ID: {last_human_id}")

    # Perform rewind
    orchestrator = RewindOrchestrator(event_bus=system_bus)
    rewind_result = await orchestrator.perform_rewind(
        thread_id=thread_id,
        target_message_id=str(last_human_id),
        include_target=False,
        revert_files=False,
        reset_state=True,
        reason="retry"
    )
    print(f"  Rewind result: {rewind_result}")

    # Record state after rewind
    msgs_after_rewind = await get_current_state_messages(graph, base_config)
    cp_after_rewind = await count_checkpoints(saver, base_config)
    counts_after_rewind = count_messages_by_type(msgs_after_rewind)

    print(f"\n  After rewind:")
    print(f"    Checkpoints: {cp_after_rewind}")
    print(f"    State messages: {len(msgs_after_rewind)} (human={counts_after_rewind['human']}, ai={counts_after_rewind['ai']}, tool={counts_after_rewind['tool']})")

    # =====================================================================
    # PHASE 3: Retry - resend the same message
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Retry - resend round 3 message")
    print("=" * 70)

    # Reset engine counters so Supervisor behaves the same
    mock_engine.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    msg = "Round 3 HumanMessage"
    await graph.ainvoke(AgentState(messages=[HumanMessage(content=msg)]), config=base_config)
    await persist_messages_for_round(thread_id, project_id, 3)
    print(f"  Retry round completed")

    # Record state after retry
    msgs_after_retry = await get_current_state_messages(graph, base_config)
    cp_after_retry = await count_checkpoints(saver, base_config)
    counts_after_retry = count_messages_by_type(msgs_after_retry)

    print(f"\n  After retry:")
    print(f"    Checkpoints: {cp_after_retry}")
    print(f"    State messages: {len(msgs_after_retry)} (human={counts_after_retry['human']}, ai={counts_after_retry['ai']}, tool={counts_after_retry['tool']})")

    # =====================================================================
    # PHASE 4: Verify DB messages table
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 4: Verify Messages Table")
    print("=" * 70)

    async with session_scope() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM messages WHERE thread_id = :tid"),
            {"tid": thread_id}
        )
        total_db_msgs = result.scalar()

        result = await session.execute(
            text("SELECT role, COUNT(*) FROM messages WHERE thread_id = :tid GROUP BY role"),
            {"tid": thread_id}
        )
        role_counts = dict(result.fetchall())

    print(f"  DB messages: {total_db_msgs}")
    print(f"  Role distribution: {role_counts}")

    # =====================================================================
    # ASSERTIONS
    # =====================================================================
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    passed = True

    # After 3 rounds: should have 3 human messages + some AI messages
    if counts_after_3['human'] == 3:
        print(f"  PASS: After 3 rounds, human messages = 3")
    else:
        print(f"  FAIL: After 3 rounds, human messages = {counts_after_3['human']} (expected 3)")
        passed = False

    # After rewind: should have fewer messages (last human and after removed)
    # The rewind removes from last human onward, so we should lose round 3's human + all AI after it
    if len(msgs_after_rewind) < len(msgs_after_3):
        print(f"  PASS: After rewind, messages reduced: {len(msgs_after_3)} -> {len(msgs_after_rewind)}")
    else:
        print(f"  FAIL: After rewind, messages NOT reduced: {len(msgs_after_3)} -> {len(msgs_after_rewind)}")
        passed = False

    # After retry: should have messages restored (but maybe different count due to new generation)
    if len(msgs_after_retry) >= len(msgs_after_rewind):
        print(f"  PASS: After retry, messages restored: {len(msgs_after_rewind)} -> {len(msgs_after_retry)}")
    else:
        print(f"  FAIL: After retry, messages decreased: {len(msgs_after_rewind)} -> {len(msgs_after_retry)}")
        passed = False

    # Check DB has correct number of messages (3 rounds * 2 messages per round = 6)
    if total_db_msgs >= 6:
        print(f"  PASS: DB messages >= 6: {total_db_msgs}")
    else:
        print(f"  FAIL: DB messages < 6: {total_db_msgs}")
        passed = False

    if passed:
        print(f"\n  ALL ASSERTIONS PASSED!")
    else:
        print(f"\n  SOME ASSERTIONS FAILED")

    # Cleanup
    pruner_module.auto_prune_on_completion = original_auto_prune
    InternalLLMService.invoke = _orig_llm_invoke
    system_bus.clear()

    await cp_conn.close()
    await db_resource_manager.shutdown()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)


if __name__ == "__main__":
    asyncio.run(main())
