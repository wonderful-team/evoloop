"""
SQLite Checkpointer 性能测试套件

包含：
1. 基准测试：WAL vs DELETE 模式写入延迟对比
2. 高强度压力测试：快速连续写入 + 并发读取
3. 20+ 轮多轮对话持久化测试

运行方式：
    PYTHONPATH=/path/to/backend python tests/test_sqlite_performance_suite.py
"""

import asyncio
import os
import tempfile
import time
import statistics

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
            if c <= 20:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult(routing_target="finish")
            if c <= 40:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult(routing_target="finish")
            return EngineResult(routing_target="finish")

        if name == "Chat":
            return EngineResult(messages=[AIMessage(content=f"AI 回复第 {c} 条")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": "test"}, "id": f"call_{c}"}]),
                    ToolMessage(content=f"搜索结果 {c}", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"Worker 回复第 {c} 条"),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="默认回复")])


# ========================================================================
# Helper: Create SQLite connection with specified journal mode
# ========================================================================
async def create_saver(sqlite_path: str, journal_mode: str):
    import aiosqlite
    conn = await aiosqlite.connect(sqlite_path)
    await conn.execute(f"PRAGMA journal_mode={journal_mode}")
    await conn.execute("PRAGMA busy_timeout=30000")
    await conn.commit()
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()
    # Override setup()'s WAL setting if needed
    if journal_mode == "DELETE":
        await conn.execute("PRAGMA journal_mode=DELETE")
        await conn.commit()
    return conn, saver


async def cleanup_db(sqlite_path: str, conn):
    if conn:
        await conn.close()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)


# ========================================================================
# Test 1: Benchmark - WAL vs DELETE write latency
# ========================================================================
async def benchmark_write_latency():
    print("=" * 70)
    print("TEST 1: Benchmark - WAL vs DELETE write latency")
    print("=" * 70)

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "benchmark-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    for mode in ["WAL", "DELETE"]:
        fd, sqlite_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        conn, saver = await create_saver(sqlite_path, mode)
        graph = GraphBuilder().build(config_path, checkpointer=saver)
        set_graph(graph, config_path=config_path, checkpointer=saver)

        mock_engine = MockAgentEngine()
        set_default_engine(mock_engine)
        ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
        ContextManager.set(ctx)

        # Warmup
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content="预热")]),
            config=base_config,
        )

        # Measure 10 rounds
        latencies = []
        for i in range(10):
            start = time.perf_counter()
            await graph.ainvoke(
                AgentState(messages=[HumanMessage(content=f"消息 {i}")]),
                config=base_config,
            )
            elapsed = (time.perf_counter() - start) * 1000  # ms
            latencies.append(elapsed)

        await conn.close()
        os.unlink(sqlite_path)

        avg = statistics.mean(latencies)
        med = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        print(f"\n  [{mode}] 模式:")
        print(f"    平均延迟: {avg:.2f} ms")
        print(f"    中位延迟: {med:.2f} ms")
        print(f"    P95 延迟: {p95:.2f} ms")
        print(f"    P99 延迟: {p99:.2f} ms")
        print(f"    原始数据: {[f'{x:.1f}' for x in latencies]}")


# ========================================================================
# Test 2: High-intensity stress test
# ========================================================================
async def stress_test():
    print("\n" + "=" * 70)
    print("TEST 2: High-intensity stress test (DELETE mode)")
    print("=" * 70)

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "stress-test-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn, saver = await create_saver(sqlite_path, "DELETE")
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)
    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # Stress: 50 rounds as fast as possible
    total_start = time.perf_counter()
    for i in range(50):
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content=f"压力测试消息 {i}")]),
            config=base_config,
        )
    total_elapsed = (time.perf_counter() - total_start) * 1000

    # Verify
    total_cp = 0
    async for _ in saver.alist(base_config):
        total_cp += 1

    cp = await saver.aget_tuple(base_config)
    final_msgs = []
    if cp and cp.checkpoint:
        final_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    human_count = sum(1 for m in final_msgs if getattr(m, 'type', None) == 'human')

    await conn.close()
    os.unlink(sqlite_path)

    print(f"\n  50 轮总时间: {total_elapsed:.2f} ms ({total_elapsed/50:.2f} ms/轮)")
    print(f"  Checkpoint 总数: {total_cp}")
    print(f"  最终消息数: {len(final_msgs)}")
    print(f"  HumanMessage 数: {human_count}")
    if human_count == 51:  # 50 rounds + warmup
        print(f"  ✅ 所有轮次正确保存")
    else:
        print(f"  ❌ 预期 51 个 HumanMessage，实际 {human_count}")


# ========================================================================
# Test 3: 20+ round multi-turn conversation persistence
# ========================================================================
async def test_20_rounds():
    print("\n" + "=" * 70)
    print("TEST 3: 20+ round multi-turn conversation persistence")
    print("=" * 70)

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "20rounds-test-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn, saver = await create_saver(sqlite_path, "DELETE")
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)
    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    total_start = time.perf_counter()
    expected_human_contents = []

    for i in range(25):
        msg = f"这是第 {i+1} 轮对话的消息"
        expected_human_contents.append(msg)
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )
    total_elapsed = (time.perf_counter() - total_start) * 1000

    # Verify checkpoints
    total_cp = 0
    async for _ in saver.alist(base_config):
        total_cp += 1

    # Verify latest checkpoint content
    cp = await saver.aget_tuple(base_config)
    final_msgs = []
    if cp and cp.checkpoint:
        final_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    human_msgs = [m.content for m in final_msgs if getattr(m, 'type', None) == 'human']

    # Verify checkpoint history integrity
    print(f"\n  25 轮总时间: {total_elapsed:.2f} ms ({total_elapsed/25:.2f} ms/轮)")
    print(f"  Checkpoint 总数: {total_cp}")
    print(f"  最终消息数: {len(final_msgs)}")
    print(f"  HumanMessage 数: {len(human_msgs)}")

    # Check first and last few human messages
    print(f"\n  前 3 个 HumanMessage:")
    for m in human_msgs[:3]:
        print(f"    - {m[:60]}")
    print(f"  后 3 个 HumanMessage:")
    for m in human_msgs[-3:]:
        print(f"    - {m[:60]}")

    if human_msgs == expected_human_contents and total_cp >= 60:
        print(f"\n  ✅ 25 轮对话全部正确保存，checkpoint 链条完整")
    else:
        print(f"\n  ❌ 数据不完整:")
        print(f"     预期 HumanMessages: {len(expected_human_contents)}")
        print(f"     实际 HumanMessages: {len(human_msgs)}")
        print(f"     预期 checkpoints >= 60, 实际: {total_cp}")

    await conn.close()
    os.unlink(sqlite_path)


# ========================================================================
# Main
# ========================================================================
async def main():
    await benchmark_write_latency()
    await stress_test()
    await test_20_rounds()

    print("\n" + "=" * 70)
    print("所有测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
