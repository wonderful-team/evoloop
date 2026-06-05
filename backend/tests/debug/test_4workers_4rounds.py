"""
模拟生产环境：4 个 uvicorn worker 进程顺序处理同一个 thread 的 4 轮对话。

场景：
- 4 个独立进程，各自有独立的 graph 和 checkpointer 实例
- 但都连接到同一个 SQLite 文件
- 每轮对话由不同的进程处理

验证：checkpoint 是否会丢失或分裂。
"""

import asyncio
import multiprocessing
import os
import tempfile

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
                return EngineResult()
            if c == 5:
                return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic="PTE")))
            if c == 6:
                return EngineResult()

        if name == "Chat":
            if c == 1:
                return EngineResult(messages=[AIMessage(content="我是 AI 助手")])
            if c == 2:
                return EngineResult(messages=[AIMessage(content="我可以写代码、回答问题")])

        if name == "Worker":
            if c == 1:
                return EngineResult(
                    messages=[
                        AIMessage(content="", tool_calls=[{"name": "list_dir", "args": {}, "id": "call_1"}]),
                        ToolMessage(content="software-ecommerce/\n├── addon/\n├── app/", name="list_dir", tool_call_id="call_1"),
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
    import aiosqlite
    conn = await aiosqlite.connect(sqlite_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=30000")
    await conn.commit()
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()
    await conn.close()


async def run_single_round(sqlite_path: str, thread_id: str, config_path: str, msg: str, process_name: str):
    """Single worker processes one round."""
    import aiosqlite

    conn = await aiosqlite.connect(sqlite_path)
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

    try:
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )
    except Exception as e:
        print(f"[{process_name}] ERROR: {e}")

    # Read checkpoint count
    cfg = {"configurable": {"thread_id": thread_id}}
    cp_count = 0
    async for _ in saver.alist(cfg):
        cp_count += 1

    # Read latest
    cp = await saver.aget_tuple(cfg)
    latest_len = 0
    if cp and cp.checkpoint:
        latest_len = len(cp.checkpoint.get("channel_values", {}).get("messages", []))

    await conn.close()
    return process_name, cp_count, latest_len


def worker_process(sqlite_path: str, thread_id: str, config_path: str, msg: str, process_name: str):
    return asyncio.run(run_single_round(sqlite_path, thread_id, config_path, msg, process_name))


async def main():
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "4workers-test-thread"

    print("=" * 70)
    print("TEST: 4 separate processes each handle 1 round sequentially")
    print("=" * 70)

    await init_db(sqlite_path)

    rounds = [
        ("Round-1", "你是谁"),
        ("Round-2", "你能干什么"),
        ("Round-3", "当前是什么样的项目？"),
        ("Round-4", "PTE 是什么"),
    ]

    results = []
    for proc_name, msg in rounds:
        print(f"\n  Running {proc_name} in new process...")
        with multiprocessing.Pool(1) as pool:
            result = pool.apply(worker_process, (sqlite_path, thread_id, config_path, msg, proc_name))
            results.append(result)
        print(f"    -> {result[0]}: {result[1]} total checkpoints, {result[2]} msgs in latest")

    # Final verification
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION (fresh connection)")
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
    print(f"  Latest checkpoint messages: {len(final_msgs)}")
    for i, m in enumerate(final_msgs):
        content = str(getattr(m, 'content', ''))[:50]
        print(f"    [{i}] {type(m).__name__}: {content}")

    human_msgs = [m.content for m in final_msgs if isinstance(m, HumanMessage)]
    print(f"\n  HumanMessages in latest checkpoint: {human_msgs}")

    expected = ["你是谁", "你能干什么", "当前是什么样的项目？", "PTE 是什么"]
    if human_msgs == expected:
        print(f"\n  ✅ All 4 rounds preserved correctly!")
    else:
        print(f"\n  ❌ MISSING or OUT OF ORDER!")
        print(f"     Expected: {expected}")
        print(f"     Got:      {human_msgs}")
        print(f"\n  This is the ROOT CAUSE: each new process starts from")
        print(f"  whatever 'latest' checkpoint UUID order returns, not")
        print(f"  necessarily the truly last written checkpoint chain!")

    os.unlink(sqlite_path)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    asyncio.run(main())
