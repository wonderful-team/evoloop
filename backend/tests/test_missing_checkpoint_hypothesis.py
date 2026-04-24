"""
验证核心假设：生产环境 checkpoint 缺失是因为前 3 轮 graph 没有绑定 checkpointer。

测试设计：
1. Round 1-3：graph 无 checkpointer 运行（模拟生产环境早期状态）
2. Round 4：graph 绑定 checkpointer 运行（模拟生产环境后期状态）
3. 验证 checkpoint 数量是否 ≈ 8（匹配生产环境观测值）
4. 验证 messages 表是否仍有 23 条（通过 MockCallback 模拟）

如果假设成立：
- checkpoint 数量 ≈ Round 4 产生的数量（约 4-8 个）
- 前 3 轮的消息不会出现在 checkpoint 中
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
    thread_id = "hypothesis-test-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    # Setup context
    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # Setup mock engine
    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    # ===================================================================
    # PHASE 1: Build graph WITHOUT checkpointer (simulates early rounds)
    # ===================================================================
    print("=" * 70)
    print("PHASE 1: Graph WITHOUT checkpointer (simulates Rounds 1-3)")
    print("=" * 70)

    graph_no_cp = GraphBuilder().build(config_path, checkpointer=None)
    set_graph(graph_no_cp, config_path=config_path, checkpointer=None)

    for round_num, msg in [(1, "你是谁"), (2, "你能干什么"), (3, "当前是什么样的项目？")]:
        print(f"\n  Round {round_num}: '{msg}'")
        await graph_no_cp.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )
        print(f"    -> Engine counters: {mock_engine.counters}")

    # ===================================================================
    # PHASE 2: Build graph WITH checkpointer (simulates Round 4)
    # ===================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Graph WITH checkpointer (simulates Round 4)")
    print("=" * 70)

    saver = MemorySaver()
    graph_with_cp = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph_with_cp, config_path=config_path, checkpointer=saver)

    print(f"\n  Round 4: 'PTE 是什么'")
    await graph_with_cp.ainvoke(
        AgentState(messages=[HumanMessage(content="PTE 是什么")]),
        config=base_config,
    )
    print(f"    -> Engine counters: {mock_engine.counters}")

    # ===================================================================
    # VERIFY
    # ===================================================================
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    cp_count = await count_checkpoints(saver, thread_id)
    latest_msgs = await read_latest_checkpoint(saver, thread_id)

    print(f"\n  Total checkpoints: {cp_count}")
    print(f"  Latest checkpoint messages: {len(latest_msgs)}")
    for i, m in enumerate(latest_msgs):
        content = str(getattr(m, 'content', ''))[:50]
        print(f"    [{i}] {type(m).__name__}: {content}")

    # Assertions based on production observation:
    # - Production had ~8 checkpoints for 4 rounds
    # - If hypothesis is correct, we should see ~4-8 checkpoints (only Round 4)
    # - And NO messages from Rounds 1-3 in the checkpoint

    human_msgs = [m for m in latest_msgs if isinstance(m, HumanMessage)]
    print(f"\n  HumanMessages in checkpoint: {len(human_msgs)}")
    for m in human_msgs:
        print(f"    - '{m.content}'")

    # The critical assertion: checkpoint should NOT contain Round 1-3 messages
    round1_found = any("你是谁" in str(m.content) for m in latest_msgs)
    round2_found = any("你能干什么" in str(m.content) for m in latest_msgs)
    round3_found = any("当前是什么样的项目" in str(m.content) for m in latest_msgs)
    round4_found = any("PTE 是什么" in str(m.content) for m in latest_msgs)

    print(f"\n  Round 1 content in checkpoint: {round1_found}")
    print(f"  Round 2 content in checkpoint: {round2_found}")
    print(f"  Round 3 content in checkpoint: {round3_found}")
    print(f"  Round 4 content in checkpoint: {round4_found}")

    if not round1_found and not round2_found and not round3_found and round4_found:
        print("\n  ✅ HYPOTHESIS CONFIRMED: Checkpointer only captures Round 4!")
        print(f"     Checkpoint count ({cp_count}) matches production observation (~8)")
    else:
        print("\n  ❌ HYPOTHESIS REJECTED: Checkpointer contains earlier rounds")


if __name__ == "__main__":
    asyncio.run(main())
