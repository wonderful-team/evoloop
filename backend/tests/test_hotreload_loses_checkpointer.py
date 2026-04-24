"""
验证假设：get_graph() 热重载时如果 _checkpointer 为 None，
会重建一个无 checkpointer 的 graph，导致后续 checkpoint 丢失。

测试步骤：
1. Round 1-2：正常 graph + checkpointer 运行
2. 模拟热重载：但 _checkpointer 被设为 None
3. Round 3-4：热重载后的 graph 运行（无 checkpointer）
4. 验证：checkpoint 是否只包含 Round 1-2，而缺失 Round 3-4
"""

import asyncio
import os

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph, get_graph, _graph, _checkpointer, _config_path, _last_load_time

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


async def count_checkpoints(saver, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    count = 0
    try:
        async for _ in saver.alist(cfg):
            count += 1
    except Exception:
        pass
    return count


async def read_latest_checkpoint(saver, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    cp = await saver.aget_tuple(cfg)
    if cp is None:
        return []
    return cp.checkpoint.get("channel_values", {}).get("messages", [])


async def main():
    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    thread_id = "hotreload-test-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    # ===================================================================
    # PHASE 1: Normal graph with checkpointer (Rounds 1-2)
    # ===================================================================
    print("=" * 70)
    print("PHASE 1: Normal graph WITH checkpointer (Rounds 1-2)")
    print("=" * 70)

    saver = MemorySaver()
    graph_with_cp = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph_with_cp, config_path=config_path, checkpointer=saver)

    for round_num, msg in [(1, "你是谁"), (2, "你能干什么")]:
        print(f"\n  Round {round_num}: '{msg}'")
        await graph_with_cp.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )

    cp_count_1 = await count_checkpoints(saver, thread_id)
    msgs_1 = await read_latest_checkpoint(saver, thread_id)
    print(f"\n  After Rounds 1-2: {cp_count_1} checkpoints, {len(msgs_1)} msgs")
    for i, m in enumerate(msgs_1):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:40]}")

    # ===================================================================
    # PHASE 2: Simulate hot reload with _checkpointer = None
    # ===================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Simulate HOT RELOAD with _checkpointer = None")
    print("=" * 70)

    # This simulates the exact scenario: _checkpointer gets set to None,
    # then get_graph() triggers a rebuild with checkpointer=None
    import app.core.globals as globals_module
    globals_module._checkpointer = None
    globals_module._last_load_time = 0  # Force rebuild

    graph_after_reload = get_graph()
    print(f"\n  Graph after reload: {graph_after_reload}")
    print(f"  Graph checkpointer: {getattr(graph_after_reload, 'checkpointer', 'NO ATTRIBUTE')}")

    # ===================================================================
    # PHASE 3: Run Rounds 3-4 with the reloaded graph (no checkpointer)
    # ===================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Run Rounds 3-4 with reloaded graph (NO checkpointer)")
    print("=" * 70)

    for round_num, msg in [(3, "当前是什么样的项目？"), (4, "PTE 是什么")]:
        print(f"\n  Round {round_num}: '{msg}'")
        await graph_after_reload.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )

    # ===================================================================
    # VERIFY
    # ===================================================================
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Check original checkpointer (should only have Rounds 1-2)
    cp_count_final = await count_checkpoints(saver, thread_id)
    msgs_final = await read_latest_checkpoint(saver, thread_id)

    print(f"\n  Original checkpointer: {cp_count_final} checkpoints, {len(msgs_final)} msgs")
    for i, m in enumerate(msgs_final):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:40]}")

    round3_found = any("当前是什么样的项目" in str(getattr(m, 'content', '')) for m in msgs_final)
    round4_found = any("PTE 是什么" in str(getattr(m, 'content', '')) for m in msgs_final)

    print(f"\n  Round 3 in original checkpointer: {round3_found}")
    print(f"  Round 4 in original checkpointer: {round4_found}")

    if not round3_found and not round4_found:
        print("\n  ✅ CONFIRMED: Hot reload with _checkpointer=None causes")
        print("     subsequent rounds to be LOST from original checkpointer!")
    else:
        print("\n  ❌ Rounds 3-4 unexpectedly found in original checkpointer")


if __name__ == "__main__":
    asyncio.run(main())
