"""
多进程并发写入 SQLite checkpointer 测试 v2。

修复：先初始化数据库（单进程），再并发写入。
"""

import asyncio
import multiprocessing
import os
import tempfile
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph

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

    async def run_node(self, state, config, system_prompt, tools, max_steps=5, temperature=0.7, name="Agent", is_subtask=False, node_source=None, parallel_tools=False, model=None) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            if c == 1:
                return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic="intro")))
            if c == 2:
                return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic="capabilities")))
            if c == 3:
                return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic="project")))
            if c == 4:
                return EngineResult(routing_target="finish")
            if c == 5:
                return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic="PTE")))
            if c == 6:
                return EngineResult(routing_target="finish")

        if name == "Chat":
            if c == 1:
                return EngineResult(messages=[AIMessage(content="我是 AI 助手")])
            if c == 2:
                return EngineResult(messages=[AIMessage(content="我可以写代码、回答问题")])

        if name == "Worker":
            if c == 1:
                return EngineResult(
                    messages=[
                        AIMessage(content="", tool_calls=[{"name": "list_directory", "args": {}, "id": "call_1"}]),
                        ToolMessage(content="software-ecommerce/\n├── addon/\n├── app/", name="list_directory", tool_call_id="call_1"),
                        AIMessage(content="这是一个复合型项目，包含商城和插件系统。"),
                    ]
                )
            if c == 2:
                return EngineResult(
                    messages=[
                        AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": "PTE"}, "id": "call_2"}]),
                        ToolMessage(content="PTE=Pearson Test of English", name="search_web", tool_call_id="call_2"),
                        AIMessage(content="PTE 是 Pearson Test of English 的缩写。"),
                    ]
                )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="默认回复")])


async def init_db(sqlite_path: str):
    """Initialize DB with WAL mode in a single process."""
    import aiosqlite
    conn = await aiosqlite.connect(sqlite_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=30000")
    await conn.commit()
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()
    await conn.close()


async def run_rounds(sqlite_path: str, thread_id: str, config_path: str, messages: list, process_name: str):
    """Run graph rounds in a separate process."""
    import aiosqlite

    # Connect to already-initialized DB
    conn = await aiosqlite.connect(sqlite_path)
    # Note: Don't set WAL mode here, it's already set
    await conn.execute("PRAGMA busy_timeout=30000")
    await conn.commit()

    saver = AsyncSqliteSaver(conn=conn)

    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    for msg in messages:
        try:
            await graph.ainvoke(
                AgentState(messages=[HumanMessage(content=msg)]),
                config=base_config,
            )
        except Exception as e:
            print(f"[{process_name}] ERROR during '{msg}': {e}")
        await asyncio.sleep(0.02)  # Small delay to increase concurrency overlap

    # Count checkpoints
    cfg = {"configurable": {"thread_id": thread_id}}
    count = 0
    async for _ in saver.alist(cfg):
        count += 1

    # Read latest
    cp = await saver.aget_tuple(cfg)
    latest_msgs = []
    if cp and cp.checkpoint:
        latest_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    await conn.close()
    return process_name, count, len(latest_msgs)


def worker_process(sqlite_path: str, thread_id: str, config_path: str, messages: list, process_name: str):
    """Entry point for multiprocessing worker."""
    return asyncio.run(run_rounds(sqlite_path, thread_id, config_path, messages, process_name))


async def main():
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "concurrent-test-thread"

    print("=" * 70)
    print("TEST: Two processes writing to SAME SQLite checkpointer concurrently")
    print("=" * 70)
    print(f"SQLite path: {sqlite_path}")

    # Step 1: Initialize DB
    print("\n[Step 1] Initializing DB...")
    await init_db(sqlite_path)
    print("  DB initialized with WAL mode")

    # Step 2: Concurrent writes
    msgs_a = ["你是谁", "你能干什么"]
    msgs_b = ["当前是什么样的项目？", "PTE 是什么"]

    print("\n[Step 2] Starting Process A and Process B concurrently...")
    start_time = time.time()

    with multiprocessing.Pool(2) as pool:
        result_a = pool.apply_async(worker_process, (sqlite_path, thread_id, config_path, msgs_a, "Process-A"))
        result_b = pool.apply_async(worker_process, (sqlite_path, thread_id, config_path, msgs_b, "Process-B"))

        name_a, cp_a, msg_a = result_a.get(timeout=60)
        name_b, cp_b, msg_b = result_b.get(timeout=60)

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"  {name_a}: {cp_a} checkpoints, {msg_a} final messages")
    print(f"  {name_b}: {cp_b} checkpoints, {msg_b} final messages")

    # Step 3: Verify from fresh connection
    print("\n" + "=" * 70)
    print("VERIFICATION (fresh connection)")
    print("=" * 70)

    import aiosqlite
    conn = await aiosqlite.connect(sqlite_path)
    saver = AsyncSqliteSaver(conn=conn)

    cfg = {"configurable": {"thread_id": thread_id}}
    total_cp = 0
    async for _ in saver.alist(cfg):
        total_cp += 1

    cp = await saver.aget_tuple(cfg)
    final_msgs = []
    if cp and cp.checkpoint:
        final_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    await conn.close()

    print(f"\n  Total checkpoints in DB: {total_cp}")
    print(f"  Final message count: {len(final_msgs)}")
    for i, m in enumerate(final_msgs):
        content = str(getattr(m, 'content', ''))[:50]
        print(f"    [{i}] {type(m).__name__}: {content}")

    human_msgs = [m for m in final_msgs if isinstance(m, HumanMessage)]
    print(f"\n  HumanMessages: {len(human_msgs)}")
    for m in human_msgs:
        print(f"    - '{m.content}'")

    # Check for missing rounds
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    expected = {"你是谁", "你能干什么", "当前是什么样的项目？", "PTE 是什么"}
    actual = {m.content for m in human_msgs}
    missing = expected - actual

    if missing:
        print(f"\n  ❌ MISSING: {missing}")
        print(f"     -> Concurrent writes caused checkpoint data loss!")
    else:
        print(f"\n  ✅ All 4 HumanMessages present")

    # Check checkpoint count
    # Each round should produce ~5 checkpoints (entry + nodes)
    # 4 rounds = ~20 checkpoints
    # If concurrent writes work correctly, we should see close to 20
    if total_cp < 15:
        print(f"  ⚠️  Only {total_cp} checkpoints (expected ~20 for 4 rounds)")
        print(f"     -> Some checkpoints were lost or overwritten!")
    else:
        print(f"  ✅ Total checkpoints: {total_cp} (~expected)")

    # Cleanup
    os.unlink(sqlite_path)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    asyncio.run(main())
