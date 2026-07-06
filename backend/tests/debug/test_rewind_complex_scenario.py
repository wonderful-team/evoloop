"""
Complex rewind rollback test: 8 rounds, mixed Chat/Worker paths,
multiple operation types per domain, retry round 5.
"""

import asyncio
import os
import tempfile
from pathlib import Path

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
    """Mock engine: odd rounds -> Chat, even rounds -> Worker (with tool calls)."""
    def __init__(self):
        super().__init__()
        self.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    async def run_node(self, state, config, system_prompt, tools, max_steps=5, temperature=0.7, name="Agent", is_subtask=False, node_source=None, parallel_tools=False, model=None) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            # Odd supervisor calls -> Chat, even -> Worker
            if c % 2 == 1:
                return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic=f"topic{c}")))
            else:
                return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic=f"topic{c}")))

        if name == "Chat":
            return EngineResult(messages=[AIMessage(content=f"[Chat] Detailed response for round {c} with analysis and summary.")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{
                        "name": "search_web", "args": {"query": f"complex_query_{c}"}, "id": f"call_{c}"
                    }]),
                    ToolMessage(content=f"[Tool] Search results for query {c}: multiple findings.", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"[Worker] Synthesized answer for round {c} based on tool output."),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="default reply")])


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


async def db_snapshot(sqlite_path, thread_id):
    import aiosqlite
    async with aiosqlite.connect(sqlite_path) as conn:
        async def _cnt(table, where_col, where_val=None):
            if where_col:
                cur = await conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where_col} = ?", (where_val or thread_id,))
            else:
                cur = await conn.execute(f"SELECT COUNT(*) FROM {table}")
            return (await cur.fetchone())[0]

        # Note: todos uses source_conversation_id not thread_id
        cur = await conn.execute("SELECT COUNT(*) FROM todos WHERE source_conversation_id = ?", (thread_id,))
        todo_cnt = (await cur.fetchone())[0]

        # File ops by operation type
        cur = await conn.execute(
            "SELECT operation, COUNT(*) FROM file_operations WHERE thread_id = ? GROUP BY operation",
            (thread_id,)
        )
        file_ops_by_type = dict(await cur.fetchall())

        # Messages by role
        cur = await conn.execute(
            "SELECT role, COUNT(*) FROM messages WHERE thread_id = ? GROUP BY role",
            (thread_id,)
        )
        msg_by_role = dict(await cur.fetchall())

        # Trace events by event_type
        cur = await conn.execute(
            "SELECT event_type, COUNT(*) FROM trace_events WHERE thread_id = ? GROUP BY event_type",
            (thread_id,)
        )
        trace_by_type = dict(await cur.fetchall())

        return {
            "checkpoints": await _cnt("checkpoints", "thread_id"),
            "writes": await _cnt("writes", "thread_id"),
            "messages": sum(msg_by_role.values()),
            "msg_by_role": msg_by_role,
            "file_ops": sum(file_ops_by_type.values()),
            "file_ops_by_type": file_ops_by_type,
            "todos": todo_cnt,
            "traces": await _cnt("trace_events", "thread_id"),
            "trace_by_type": trace_by_type,
            "msg_refs": await _cnt("message_references", ""),
        }


async def persist_round_rich(session, thread_id, project_id, round_num, temp_dir):
    """Persist rich cross-domain data for a single round."""
    from uuid import uuid4
    from sqlalchemy import select, desc
    from app.models import Message, MessageReference
    from app.models.file_operation import FileOperation
    from app.models.todo import TodoItem, TodoStatus
    from app.models.learning import TraceEvent

    stmt = select(Message.id).where(Message.thread_id == thread_id).order_by(desc(Message.sequence_number)).limit(1)

    # Human message
    res = await session.execute(stmt)
    parent_id = res.scalar_one_or_none()
    hm = Message(
        thread_id=thread_id, project_id=project_id, role="human",
        content=f"Round {round_num} complex query with attachments and context.",
        sequence_number=round_num * 100,
        parent_id=parent_id, is_visible=True, category="user", action_type="text",
    )
    session.add(hm)
    await session.flush()

    # AI message (chat or worker summary)
    res = await session.execute(stmt)
    parent_id = res.scalar_one_or_none()
    is_worker_round = (round_num % 2 == 0)
    ai_content = (
        f"[Worker] Round {round_num} synthesis after tool execution."
        if is_worker_round else
        f"[Chat] Round {round_num} direct AI response with reasoning."
    )
    am = Message(
        thread_id=thread_id, project_id=project_id, role="ai",
        content=ai_content, sequence_number=round_num * 100 + 1,
        parent_id=parent_id, is_visible=True,
        category="assistant_response" if not is_worker_round else "assistant_tool_call",
        action_type="text" if not is_worker_round else "tool_call",
    )
    session.add(am)
    await session.flush()

    # Message reference
    session.add(MessageReference(
        id=str(uuid4()), message_id=am.id, type="reply", target_id=str(hm.id),
        target_name=f"Round {round_num} human",
    ))
    await session.flush()

    # Worker rounds: add tool call AI + tool output messages
    if is_worker_round:
        # Tool call AI message
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        tcm = Message(
            thread_id=thread_id, project_id=project_id, role="ai",
            content="", sequence_number=round_num * 100 + 2,
            parent_id=parent_id, is_visible=True,
            category="assistant_tool_call", action_type="tool_call",
            tool_calls=[{"name": "search_web", "args": {"query": f"q{round_num}"}, "id": f"tc_{round_num}"}],
        )
        session.add(tcm)
        await session.flush()

        # Tool output message
        res = await session.execute(stmt)
        parent_id = res.scalar_one_or_none()
        tom = Message(
            thread_id=thread_id, project_id=project_id, role="tool",
            content=f"[ToolOutput] Detailed search results for round {round_num}.",
            sequence_number=round_num * 100 + 3,
            parent_id=parent_id, is_visible=True,
            category="tool_output", action_type="tool_output",
            tool_name="search_web", tool_call_id=f"tc_{round_num}",
        )
        session.add(tom)
        await session.flush()

        # Reference: tool output -> tool call
        session.add(MessageReference(
            id=str(uuid4()), message_id=tom.id, type="tool_result",
            target_id=str(tcm.id), target_name=f"tool_call_r{round_num}",
        ))
        await session.flush()

    # FileOperation on rounds 3, 5, 7
    if round_num in (3, 5, 7):
        op_type = {3: "ADD", 5: "EDIT", 7: "DELETE"}[round_num]
        file_path = temp_dir / f"test_file_r{round_num}.py"
        # Create physical file for ADD/EDIT so FileRewind has something to revert
        if op_type in ("ADD", "EDIT"):
            file_path.write_text(f"# original content for round {round_num}\n", encoding="utf-8")
        session.add(FileOperation(
            thread_id=thread_id, message_id=am.id,
            file_path=str(file_path),
            operation=op_type,
            original_content=f"# backup content for round {round_num}\n" if op_type in ("EDIT", "DELETE") else None,
        ))
        await session.flush()

    # TodoItem on rounds 2, 4, 6
    if round_num in (2, 4, 6):
        status = TodoStatus.COMPLETED if round_num == 6 else TodoStatus.PENDING
        session.add(TodoItem(
            source_conversation_id=thread_id, source_message_id=str(am.id),
            title=f"Action item from round {round_num}",
            description=f"Detailed todo description for round {round_num} with steps.",
            status=status,
        ))
        await session.flush()

    # TraceEvent on rounds 3, 5, 7
    if round_num in (3, 5, 7):
        session.add(TraceEvent(
            thread_id=thread_id, message_id=am.id, step_number=round_num,
            node_name=f"worker_node_r{round_num}", action_type="tool_call",
            state_snapshot=f'{{"round": {round_num}, "context": "rich"}}',
            action_payload=f'{{"tool": "search_web", "round": {round_num}}}',
            event_type="tool_call",
        ))
        await session.flush()

    return hm.id


async def main():
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["SQLITE_DB_PATH"] = sqlite_path
    from app.core.config import settings
    settings.SQLITE_PATH = sqlite_path

    temp_dir = Path(tempfile.mkdtemp(prefix="rewind_test_"))

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

    thread_id = "rewind-complex-thread"
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
        return type('R', (), {'content': 'Mock audit summary.'})()
    InternalLLMService.invoke = mock_llm

    # =====================================================================
    # PHASE 1: Run 8 rounds with rich cross-domain data
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: Run 8 rounds (mixed Chat/Worker + rich domain data)")
    print("=" * 70)

    human_msg_ids = []
    for i in range(8):
        r = i + 1
        await graph.ainvoke(AgentState(messages=[HumanMessage(content=f"Round {r}")]), config=base_config)
        async with session_scope() as session:
            hm_id = await persist_round_rich(session, thread_id, project_id, r, temp_dir)
            human_msg_ids.append(hm_id)
        path_type = "Worker" if (r % 2 == 0) else "Chat"
        print(f"  Round {r} done ({path_type})  human_msg_id={hm_id}")

    db_before = await db_snapshot(sqlite_path, thread_id)
    msgs_before = await get_state_msgs(graph, base_config)
    print(f"\n  BEFORE rewind:")
    print(f"    State messages: {len(msgs_before)}  {count_by_type(msgs_before)}")
    print(f"    Checkpoints: {db_before['checkpoints']}  Writes: {db_before['writes']}")
    print(f"    Messages: {db_before['messages']} {db_before['msg_by_role']}")
    print(f"    FileOps: {db_before['file_ops']} {db_before['file_ops_by_type']}")
    print(f"    Todos: {db_before['todos']}  Traces: {db_before['traces']} {db_before['trace_by_type']}")
    print(f"    MsgRefs: {db_before['msg_refs']}")

    # =====================================================================
    # PHASE 2: Retry round 5 with ALL handlers
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Retry round 5 (mid-conversation, mixed path)")
    print("=" * 70)

    from app.core.events import system_bus
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.rewind.state import StateRewind
    from app.core.engine.rewind.checkpoint import CheckpointRewind
    from app.core.engine.rewind.message import MessageRewind
    from app.core.file.rewind import FileRewind
    from app.domain.todo.rewind import TodoRewind
    from app.core.learning.rewind import TraceRewind

    StateRewind.register(system_bus)
    CheckpointRewind.register(system_bus)
    MessageRewind.register(system_bus)
    FileRewind.register(system_bus)
    TodoRewind.register(system_bus)
    TraceRewind.register(system_bus)

    target_id = human_msg_ids[4]  # round 5
    print(f"  Target: message_id={target_id} (Round 5)")

    orchestrator = RewindOrchestrator(event_bus=system_bus)
    result = await orchestrator.perform_rewind(
        thread_id=thread_id,
        target_message_id=str(target_id),
        include_target=False,
        revert_files=True,
        reset_state=True,
        reason="retry"
    )
    print(f"\n  Rewind result: {result}")

    db_after = await db_snapshot(sqlite_path, thread_id)
    msgs_after = await get_state_msgs(graph, base_config)
    print(f"\n  AFTER rewind:")
    print(f"    State messages: {len(msgs_after)}  {count_by_type(msgs_after)}")
    print(f"    Checkpoints: {db_after['checkpoints']}  Writes: {db_after['writes']}")
    print(f"    Messages: {db_after['messages']} {db_after['msg_by_role']}")
    print(f"    FileOps: {db_after['file_ops']} {db_after['file_ops_by_type']}")
    print(f"    Todos: {db_after['todos']}  Traces: {db_after['traces']} {db_after['trace_by_type']}")
    print(f"    MsgRefs: {db_after['msg_refs']}")

    # =====================================================================
    # PHASE 3: Re-run rounds 5-8
    # =====================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Re-run rounds 5-8")
    print("=" * 70)

    mock_engine.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    for r in [5, 6, 7, 8]:
        await graph.ainvoke(AgentState(messages=[HumanMessage(content=f"Round {r}")]), config=base_config)
        async with session_scope() as session:
            await persist_round_rich(session, thread_id, project_id, r, temp_dir)
        path_type = "Worker" if (r % 2 == 0) else "Chat"
        print(f"  Round {r} re-run done ({path_type})")

    db_final = await db_snapshot(sqlite_path, thread_id)
    msgs_final = await get_state_msgs(graph, base_config)
    print(f"\n  AFTER retry:")
    print(f"    State messages: {len(msgs_final)}  {count_by_type(msgs_final)}")
    print(f"    Checkpoints: {db_final['checkpoints']}  Writes: {db_final['writes']}")
    print(f"    Messages: {db_final['messages']} {db_final['msg_by_role']}")
    print(f"    FileOps: {db_final['file_ops']} {db_final['file_ops_by_type']}")
    print(f"    Todos: {db_final['todos']}  Traces: {db_final['traces']} {db_final['trace_by_type']}")
    print(f"    MsgRefs: {db_final['msg_refs']}")

    # =====================================================================
    # ASSERTIONS
    # =====================================================================
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    passed = True

    # State: must shrink to round 1-4 scope
    if len(msgs_after) < len(msgs_before):
        print(f"  PASS[State]: {len(msgs_before)} -> {len(msgs_after)} (rolled back to round 1-4 scope)")
    else:
        print(f"  FAIL[State]: state NOT reduced")
        passed = False

    # Checkpoints / Writes cleaned
    if db_after['checkpoints'] < db_before['checkpoints']:
        print(f"  PASS[Checkpoint]: {db_before['checkpoints']} -> {db_after['checkpoints']}")
    else:
        print(f"  FAIL[Checkpoint]: checkpoints NOT reduced")
        passed = False

    if db_after['writes'] < db_before['writes']:
        print(f"  PASS[Writes]: {db_before['writes']} -> {db_after['writes']}")
    else:
        print(f"  FAIL[Writes]: writes NOT reduced")
        passed = False

    # Messages: should drop round 6-8 data, keep round 1-5
    # Round 1-5: 5 human + 3 ai (chat) + 2*(tool_call_ai + tool_output) = 5+3+4 = 12 msgs in DB
    # But some Finish AIMessages also added by graph...
    if db_after['messages'] < db_before['messages']:
        print(f"  PASS[Message]: {db_before['messages']} -> {db_after['messages']}")
    else:
        print(f"  FAIL[Message]: messages NOT reduced")
        passed = False

    # FileOps: round 5 EDIT and round 7 DELETE should be removed (round 3 ADD kept)
    # After rewind: should have 1 file op (ADD r3) because r5's AI msg is also > target
    if db_after['file_ops'] == 1:
        print(f"  PASS[FileOp]: {db_before['file_ops']} -> {db_after['file_ops']} (kept ADD r3, removed EDIT r5 + DELETE r7)")
    else:
        print(f"  FAIL[FileOp]: expected 1, got {db_after['file_ops']}")
        passed = False

    # Todos: round 6 completed todo should be removed (round 2, 4 kept)
    if db_after['todos'] == 2:
        print(f"  PASS[Todo]: {db_before['todos']} -> {db_after['todos']} (kept r2+r4, removed r6)")
    else:
        print(f"  FAIL[Todo]: expected 2, got {db_after['todos']}")
        passed = False

    # Traces: round 5 and 7 traces should be removed (round 3 kept)
    if db_after['traces'] == 1:
        print(f"  PASS[Trace]: {db_before['traces']} -> {db_after['traces']} (kept r3, removed r5+r7)")
    else:
        print(f"  FAIL[Trace]: expected 1, got {db_after['traces']}")
        passed = False

    # MsgRefs: should be reduced (round 6-8 refs removed)
    if db_after['msg_refs'] < db_before['msg_refs']:
        print(f"  PASS[MsgRef]: {db_before['msg_refs']} -> {db_after['msg_refs']}")
    else:
        print(f"  FAIL[MsgRef]: msg_refs NOT reduced")
        passed = False

    # Retry recovery
    if len(msgs_final) >= len(msgs_after):
        print(f"  PASS[Retry-State]: restored {len(msgs_after)} -> {len(msgs_final)}")
    else:
        print(f"  FAIL[Retry-State]: state shrank after retry")
        passed = False

    if db_final['messages'] > db_after['messages']:
        print(f"  PASS[Retry-DB]: messages accumulated {db_after['messages']} -> {db_final['messages']}")
    else:
        print(f"  FAIL[Retry-DB]: messages did not grow after retry")
        passed = False

    if passed:
        print(f"\n  ALL COMPLEX SCENARIO ASSERTIONS PASSED!")
    else:
        print(f"\n  SOME ASSERTIONS FAILED")

    # Cleanup
    pruner_module.auto_prune_on_completion = orig_prune
    InternalLLMService.invoke = orig_llm
    system_bus.clear()
    await cp_conn.close()
    await db_resource_manager.shutdown()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)
    # Clean up temp files
    import shutil
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(main())
