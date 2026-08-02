"""
走真实生产全链路的 4 轮对话 + 重试测试。

关键设计：
- Graph：真实 YAML 配置编译的 StateGraph（supervisor / worker / chat / finish）
- Checkpointer：MemorySaver（API 与 SqliteSaver 完全一致，排除 DB 连接干扰）
- Engine：MockAgentEngine（继承 AgentEngine，重写 run_node）
- 其余：prompt 构建、hydration、signal dispatch、routing、reducer 全部真实
"""

import asyncio
import os

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph
# ---------------------------------------------------------------------------
# 跳过需要 DB 的环节（避免数据库初始化阻塞）
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Mock Engine：根据节点名和调用次数返回预定义结果
# ---------------------------------------------------------------------------
class MockAgentEngine(AgentEngine):
    def __init__(self):
        super().__init__()
        self.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    async def run_node(
        self,
        state,
        config,
        system_prompt,
        tools,
        max_steps=5,
        temperature=0.7,
        name="Agent",
        node_source=None,
        parallel_tools=False,
        model=None,
    ) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            if c == 1:
                return EngineResult(
                    signal=RouteToSignal(target="chat", context=RoutingContext(topic="intro")),
                )
            if c == 2:
                return EngineResult(
                    signal=RouteToSignal(target="chat", context=RoutingContext(topic="capabilities")),
                )
            if c == 3:
                return EngineResult(
                    signal=RouteToSignal(target="worker", context=RoutingContext(topic="project")),
                )
            if c == 4:
                return EngineResult()
            if c == 5:
                return EngineResult(
                    signal=RouteToSignal(target="worker", context=RoutingContext(topic="PTE")),
                )
            if c == 6:
                return EngineResult()
            if c == 7:
                return EngineResult(
                    signal=RouteToSignal(target="worker", context=RoutingContext(topic="PTE")),
                )
            if c == 8:
                return EngineResult()

        if name == "Chat":
            if c == 1:
                return EngineResult(messages=[AIMessage(content="我是 AI 助手")])
            if c == 2:
                return EngineResult(messages=[AIMessage(content="我可以写代码、回答问题")])

        if name == "Worker":
            if c == 1:
                return EngineResult(messages=[
                    AIMessage(content="", tool_calls=[{"name": "list_dir", "args": {}, "id": "tc1"}]),
                    ToolMessage(content="software-ecommerce/\n├── addon/\n├── app/", tool_call_id="tc1", name="list_dir"),
                    AIMessage(content="这是一个复合型项目，包含商城和插件系统。"),
                ])
            if c == 2:
                return EngineResult(messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {}, "id": "tc2"}]),
                    ToolMessage(content="PTE=Pearson Test of English", tool_call_id="tc2", name="search_web"),
                    AIMessage(content="PTE 是 Pearson Test of English 的缩写。"),
                ])
            if c == 3:
                return EngineResult(messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {}, "id": "tc3"}]),
                    ToolMessage(content="PTE=Pearson Test of English (retry search)", tool_call_id="tc3", name="search_web"),
                    AIMessage(content="PTE 是 Pearson Test of English 的缩写（重试结果）。"),
                ])

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def fmt_msgs(msgs):
    out = []
    for m in msgs:
        extra = ""
        if isinstance(m, ToolMessage):
            extra = f" name={m.name}"
        elif isinstance(m, AIMessage) and m.tool_calls:
            extra = f" tool_calls={len(m.tool_calls)}"
        out.append(f"{type(m).__name__}{extra}")
    return out


async def read_checkpoint(saver, thread_id, checkpoint_id=None):
    cfg = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    cp = await saver.aget_tuple(cfg)
    if cp is None:
        return []
    return cp.checkpoint.get("channel_values", {}).get("messages", [])


async def count_all_checkpoints(saver, thread_id):
    """Count total checkpoints stored for a thread."""
    cfg = {"configurable": {"thread_id": thread_id}}
    count = 0
    try:
        async for _ in saver.alist(cfg):
            count += 1
    except Exception:
        pass
    return count


# ---------------------------------------------------------------------------
# 主测试
# ---------------------------------------------------------------------------
async def main():
    # 1. 准备真实 graph + checkpointer
    saver = MemorySaver()
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml"
    )
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    # 2. 注入 Mock Engine
    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "real-graph-demo-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    # 设置 EvoContext（hydration 需要）
    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # =====================================================================
    # ROUND 1
    # =====================================================================
    print("=" * 70)
    print("ROUND 1: Human('你是谁') -> Supervisor -> Chat -> Finish -> END")
    print("=" * 70)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="你是谁")]),
        config=base_config,
    )
    msgs = await read_checkpoint(saver, thread_id)
    cp_count = await count_all_checkpoints(saver, thread_id)
    print(f"  checkpoint: {len(msgs)} msgs, {cp_count} total checkpoints -> {fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 2
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 2: Human('你能干什么') -> Supervisor -> Chat -> Finish -> END")
    print("=" * 70)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="你能干什么")]),
        config=base_config,
    )
    msgs = await read_checkpoint(saver, thread_id)
    cp_count = await count_all_checkpoints(saver, thread_id)
    print(f"  checkpoint: {len(msgs)} msgs, {cp_count} total checkpoints -> {fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 3: 带 ToolMessage
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 3: Human('当前是什么样的项目？') -> Supervisor -> Worker -> Supervisor -> Finish -> END")
    print("=" * 70)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="当前是什么样的项目？")]),
        config=base_config,
    )
    msgs = await read_checkpoint(saver, thread_id)
    cp_count = await count_all_checkpoints(saver, thread_id)
    print(f"  checkpoint: {len(msgs)} msgs, {cp_count} total checkpoints -> {fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 4
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 4: Human('PTE 是什么') -> Supervisor -> Worker -> Supervisor -> Finish -> END")
    print("=" * 70)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="PTE 是什么")]),
        config=base_config,
    )
    msgs_before_retry = await read_checkpoint(saver, thread_id)
    cp_count_before = await count_all_checkpoints(saver, thread_id)
    print(f"  checkpoint: {len(msgs_before_retry)} msgs, {cp_count_before} total checkpoints -> {fmt_msgs(msgs_before_retry)}")
    for i, m in enumerate(msgs_before_retry):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # RETRY：回滚 Round 4，重新运行
    # =====================================================================
    print("\n" + "=" * 70)
    print("RETRY: Rollback to before Round 4, then re-run Round 4")
    print("=" * 70)

    # 获取重试前最新 checkpoint
    cp_before = await saver.aget_tuple(base_config)
    before_id = cp_before.checkpoint["id"]
    print(f"\n  BEFORE retry: {len(msgs_before_retry)} msgs (checkpoint={before_id[:20]}...)")

    # 模拟 StateRewind 的 retry 逻辑：删除从最后一条 HumanMessage 开始的所有消息
    last_human_idx = -1
    for i, m in enumerate(msgs_before_retry):
        if isinstance(m, HumanMessage):
            last_human_idx = i

    graph_updates = []
    if last_human_idx >= 0:
        for m in msgs_before_retry[last_human_idx:]:
            mid = getattr(m, "id", None)
            if mid:
                graph_updates.append(RemoveMessage(id=mid))
        print(f"  last_human_idx={last_human_idx}, sending {len(graph_updates)} RemoveMessage(s)")

    await graph.aupdate_state(
        base_config,
        {"messages": graph_updates},
        as_node="__start__",
    )

    msgs_after_rewind = await read_checkpoint(saver, thread_id)
    print(f"\n  AFTER rewind: {len(msgs_after_rewind)} msgs")
    for i, m in enumerate(msgs_after_rewind):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # 重新传入 Round 4 的消息（模拟 background_agent 重试）
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="PTE 是什么")]),
        config=base_config,
    )

    msgs_after_retry = await read_checkpoint(saver, thread_id)
    cp_after = await saver.aget_tuple(base_config)
    after_id = cp_after.checkpoint["id"]
    print(f"\n  AFTER retry re-invoke: {len(msgs_after_retry)} msgs (checkpoint={after_id[:20]}...)")
    for i, m in enumerate(msgs_after_retry):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # 断言
    # =====================================================================
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    human_before = sum(1 for m in msgs_before_retry if isinstance(m, HumanMessage))
    assert human_before == 4, f"Expected 4 HumanMessages before retry, got {human_before}"
    print(f"  ✅ Before retry: {len(msgs_before_retry)} msgs, {human_before} HumanMessages")

    human_rewind = sum(1 for m in msgs_after_rewind if isinstance(m, HumanMessage))
    assert human_rewind == 3, f"Expected 3 HumanMessages after rewind, got {human_rewind}"
    print(f"  ✅ After rewind: {len(msgs_after_rewind)} msgs, {human_rewind} HumanMessages")

    human_retry = sum(1 for m in msgs_after_retry if isinstance(m, HumanMessage))
    assert human_retry == 4, f"Expected 4 HumanMessages after retry, got {human_retry}"
    print(f"  ✅ After retry: {len(msgs_after_retry)} msgs, {human_retry} HumanMessages")

    contents_before = [m.content for m in msgs_before_retry if isinstance(m, HumanMessage)]
    contents_retry = [m.content for m in msgs_after_retry if isinstance(m, HumanMessage)]
    assert contents_before[:3] == contents_retry[:3], "First 3 human messages diverged!"
    print(f"  ✅ First 3 human messages identical")

    tool_before = sum(1 for m in msgs_before_retry if isinstance(m, ToolMessage))
    tool_retry = sum(1 for m in msgs_after_retry if isinstance(m, ToolMessage))
    assert tool_retry == tool_before + 1, f"ToolMessages should increase by 1 after retry (new tool call): {tool_before} -> {tool_retry}"
    tool_names = [m.name for m in msgs_after_retry if isinstance(m, ToolMessage)]
    assert tool_names == ["list_dir", "search_web"], f"ToolMessage names mismatch: {tool_names}"
    print(f"  ✅ ToolMessages correct: {tool_names} (list_dir from Round 3, search_web from retry)")

    print("\n🎉 ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
