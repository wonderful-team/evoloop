"""
Real-graph E2E regression test: 4 rounds + retry through agent_main.yaml.

Covers the full LangGraph pipeline (supervisor → worker/chat → finish)
with real YAML compilation, prompt/hydration/signal dispatch/routing/reducer.
"""

import pytest

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.schemas import EngineResult
from app.core.engine.signals.schemas import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState


# ---------------------------------------------------------------------------
# Mock Engine: returns predefined results per node name + call counter
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
        is_subtask=False,
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
# Helpers
# ---------------------------------------------------------------------------
def _fmt_msgs(msgs):
    out = []
    for m in msgs:
        extra = ""
        if isinstance(m, ToolMessage):
            extra = f" name={m.name}"
        elif isinstance(m, AIMessage) and m.tool_calls:
            extra = f" tool_calls={len(m.tool_calls)}"
        out.append(f"{type(m).__name__}{extra}")
    return out


async def _read_checkpoint(saver, thread_id, checkpoint_id=None):
    cfg = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    cp = await saver.aget_tuple(cfg)
    if cp is None:
        return []
    return cp.checkpoint.get("channel_values", {}).get("messages", [])


async def _count_all_checkpoints(saver, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    count = 0
    try:
        async for _ in saver.alist(cfg):
            count += 1
    except Exception:
        pass
    return count


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_graph_4round_retry(agent_main_graph, memory_saver):
    """Run 4 conversation rounds through agent_main.yaml graph, then retry round 4."""
    graph = agent_main_graph
    saver = memory_saver

    # Inject mock engine
    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "real-graph-demo-thread"
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # =====================================================================
    # ROUND 1: Human("你是谁") -> Supervisor -> Chat -> Finish -> END
    # =====================================================================
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="你是谁")]),
        config=base_config,
    )
    msgs = await _read_checkpoint(saver, thread_id)
    cp_count = await _count_all_checkpoints(saver, thread_id)
    print(f"ROUND 1: {len(msgs)} msgs, {cp_count} checkpoints -> {_fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 2: Human("你能干什么") -> Supervisor -> Chat -> Finish -> END
    # =====================================================================
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="你能干什么")]),
        config=base_config,
    )
    msgs = await _read_checkpoint(saver, thread_id)
    cp_count = await _count_all_checkpoints(saver, thread_id)
    print(f"ROUND 2: {len(msgs)} msgs, {cp_count} checkpoints -> {_fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 3: Human("当前是什么样的项目？") -> Supervisor -> Worker -> Supervisor -> Finish -> END
    # =====================================================================
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="当前是什么样的项目？")]),
        config=base_config,
    )
    msgs = await _read_checkpoint(saver, thread_id)
    cp_count = await _count_all_checkpoints(saver, thread_id)
    print(f"ROUND 3: {len(msgs)} msgs, {cp_count} checkpoints -> {_fmt_msgs(msgs)}")
    for i, m in enumerate(msgs):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # ROUND 4: Human("PTE 是什么") -> Supervisor -> Worker -> Supervisor -> Finish -> END
    # =====================================================================
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="PTE 是什么")]),
        config=base_config,
    )
    msgs_before_retry = await _read_checkpoint(saver, thread_id)
    cp_count_before = await _count_all_checkpoints(saver, thread_id)
    print(f"ROUND 4: {len(msgs_before_retry)} msgs, {cp_count_before} checkpoints -> {_fmt_msgs(msgs_before_retry)}")
    for i, m in enumerate(msgs_before_retry):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # RETRY: Rollback to before Round 4, then re-run Round 4
    # =====================================================================
    print("RETRY: Rollback to before Round 4, then re-run Round 4")

    cp_before = await saver.aget_tuple(base_config)
    before_id = cp_before.checkpoint["id"]
    print(f"BEFORE retry: {len(msgs_before_retry)} msgs (checkpoint={before_id[:20]}...)")

    # Simulate StateRewind retry logic: remove messages from last HumanMessage onward
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
        print(f"last_human_idx={last_human_idx}, sending {len(graph_updates)} RemoveMessage(s)")

    await graph.aupdate_state(
        base_config,
        {"messages": graph_updates},
        as_node="__start__",
    )

    msgs_after_rewind = await _read_checkpoint(saver, thread_id)
    print(f"AFTER rewind: {len(msgs_after_rewind)} msgs")
    for i, m in enumerate(msgs_after_rewind):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # Re-invoke Round 4 (simulates background_agent retry)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="PTE 是什么")]),
        config=base_config,
    )

    msgs_after_retry = await _read_checkpoint(saver, thread_id)
    cp_after = await saver.aget_tuple(base_config)
    after_id = cp_after.checkpoint["id"]
    print(f"AFTER retry re-invoke: {len(msgs_after_retry)} msgs (checkpoint={after_id[:20]}...)")
    for i, m in enumerate(msgs_after_retry):
        print(f"  [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # =====================================================================
    # Assertions
    # =====================================================================
    human_before = sum(1 for m in msgs_before_retry if isinstance(m, HumanMessage))
    assert human_before == 4, f"Expected 4 HumanMessages before retry, got {human_before}"

    human_rewind = sum(1 for m in msgs_after_rewind if isinstance(m, HumanMessage))
    assert human_rewind == 3, f"Expected 3 HumanMessages after rewind, got {human_rewind}"

    human_retry = sum(1 for m in msgs_after_retry if isinstance(m, HumanMessage))
    assert human_retry == 4, f"Expected 4 HumanMessages after retry, got {human_retry}"

    contents_before = [m.content for m in msgs_before_retry if isinstance(m, HumanMessage)]
    contents_retry = [m.content for m in msgs_after_retry if isinstance(m, HumanMessage)]
    assert contents_before[:3] == contents_retry[:3], "First 3 human messages diverged!"

    tool_before = sum(1 for m in msgs_before_retry if isinstance(m, ToolMessage))
    tool_retry = sum(1 for m in msgs_after_retry if isinstance(m, ToolMessage))
    # Retry introduces a new tool call, so ToolMessages should increase by 1
    assert tool_retry == tool_before + 1, (
        f"ToolMessages should increase by 1 after retry: {tool_before} -> {tool_retry}"
    )
    tool_names = [m.name for m in msgs_after_retry if isinstance(m, ToolMessage)]
    assert tool_names == ["list_dir", "search_web"], f"ToolMessage names mismatch: {tool_names}"
