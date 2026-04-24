"""
实测：4 轮对话 + 重试，逐轮检查 checkpoint。

使用 MemorySaver（与 AsyncSqliteSaver API 完全一致），
排除数据库连接干扰，专注验证 checkpoint 回滚语义。
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph


class MockLLM:
    def __init__(self, responses):
        self.responses = responses
        self.call_idx = 0

    async def ainvoke(self, messages, **kwargs):
        resp = self.responses[self.call_idx]
        self.call_idx += 1
        return resp


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


async def main():
    saver = MemorySaver()

    # 4 轮对话的 LLM 响应（+1 个给重试用）
    responses = [
        AIMessage(content="我是 AI 助手"),                       # Round 1
        AIMessage(content="我可以写代码、回答问题"),              # Round 2
        AIMessage(                                              # Round 3: tool call
            content="",
            tool_calls=[{"name": "search_web", "args": {"q": "PTE"}, "id": "tc1"}],
        ),
        AIMessage(content="PTE 是 Pearson Test of English"),    # Round 3: final after tool
        AIMessage(content="不客气，有问题随时问"),                # Round 4 (first attempt)
        AIMessage(content="不客气，这是 Round 4 重试后的回复"),   # Round 4 (retry)
    ]

    llm = MockLLM(responses)

    async def agent_node(state: MessagesState, config):
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.set_entry_point("agent")
    builder.add_edge("agent", END)
    graph = builder.compile(checkpointer=saver)

    thread_id = "demo-thread-4round"

    # =====================================================================
    # ROUND 1
    # =====================================================================
    print("=" * 70)
    print("ROUND 1: Human('你是谁') -> AI")
    print("=" * 70)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="你是谁")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    msgs = await read_checkpoint(saver, thread_id)
    print(f"  checkpoint: {len(msgs)} msgs -> {fmt_msgs(msgs)}")

    # =====================================================================
    # ROUND 2
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 2: Human('你能干什么') -> AI")
    print("=" * 70)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="你能干什么")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    msgs = await read_checkpoint(saver, thread_id)
    print(f"  checkpoint: {len(msgs)} msgs -> {fmt_msgs(msgs)}")

    # =====================================================================
    # ROUND 3: 带 ToolMessage
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 3: Human('PTE 是什么') -> AI(tool_call) -> Tool -> AI")
    print("=" * 70)

    await graph.ainvoke(
        {"messages": [HumanMessage(content="PTE 是什么")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    msgs = await read_checkpoint(saver, thread_id)
    print(f"  after AI(tool_call): {len(msgs)} msgs -> {fmt_msgs(msgs)}")

    await graph.ainvoke(
        {"messages": [ToolMessage(content="PTE=Pearson Test of English", tool_call_id="tc1", name="search_web")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    msgs = await read_checkpoint(saver, thread_id)
    print(f"  after ToolMessage:   {len(msgs)} msgs -> {fmt_msgs(msgs)}")

    # =====================================================================
    # ROUND 4
    # =====================================================================
    print("\n" + "=" * 70)
    print("ROUND 4: Human('谢谢') -> AI")
    print("=" * 70)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="谢谢")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    msgs_before_retry = await read_checkpoint(saver, thread_id)
    print(f"  checkpoint: {len(msgs_before_retry)} msgs -> {fmt_msgs(msgs_before_retry)}")

    # =====================================================================
    # RETRY
    # =====================================================================
    print("\n" + "=" * 70)
    print("RETRY: Rollback Round 4, then re-run")
    print("=" * 70)

    print(f"\n  BEFORE retry: {len(msgs_before_retry)} msgs")
    for i, m in enumerate(msgs_before_retry):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # 模拟 StateRewind 的 retry 逻辑
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
        print(f"\n  last_human_idx={last_human_idx}, sending {len(graph_updates)} RemoveMessage(s)")

    await graph.aupdate_state(
        {"configurable": {"thread_id": thread_id}},
        {"messages": graph_updates},
        as_node="__start__",
    )

    msgs_after_rewind = await read_checkpoint(saver, thread_id)
    print(f"\n  AFTER rewind: {len(msgs_after_rewind)} msgs")
    for i, m in enumerate(msgs_after_rewind):
        print(f"    [{i}] {type(m).__name__}: {str(getattr(m, 'content', ''))[:45]}")

    # 重新传入 Round 4 的消息（模拟 background_agent 重试）
    await graph.ainvoke(
        {"messages": [HumanMessage(content="谢谢")]},
        config={"configurable": {"thread_id": thread_id}},
    )

    msgs_after_retry = await read_checkpoint(saver, thread_id)
    print(f"\n  AFTER retry re-invoke: {len(msgs_after_retry)} msgs")
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
    print(f"  ✅ First 3 human messages identical: {contents_before[:3]}")

    tool_before = sum(1 for m in msgs_before_retry if isinstance(m, ToolMessage))
    tool_retry = sum(1 for m in msgs_after_retry if isinstance(m, ToolMessage))
    assert tool_before == tool_retry, f"ToolMessages changed: {tool_before} -> {tool_retry}"
    print(f"  ✅ ToolMessages preserved: {tool_before}")

    print("\n🎉 ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
