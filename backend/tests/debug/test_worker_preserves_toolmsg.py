"""
Tests for ToolMessage preservation through WorkerNode.

Four levels:
  1. Unit   – process_worker_result preserves ToolMessage
  2. Integration – WorkerNode._build_fallback_outcome preserves ToolMessage
  3. E2E    – Full graph run writes ToolMessage into checkpoint
  4. Retry/Resume – Checkpoint deserialization reconstructs full ToolMessage history
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.engine.schemas import EngineResult
from app.core.engine.nodes.utils.worker_result_processor import process_worker_result
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import ExecutionTicket


# ---------------------------------------------------------------------------
# 1. UNIT TESTS
# ---------------------------------------------------------------------------

def test_process_worker_result_preserves_tool_messages():
    """
    process_worker_result must NOT drop ToolMessages.
    Before the fix it returned [AIMessage(summary)] only.
    After the fix it returns the full engine_result.messages list
    (with the last AIMessage content replaced by the summary).
    """
    engine_result = EngineResult(
        messages=[
            AIMessage(content="", tool_calls=[{"name": "list_dir", "args": {}, "id": "tc1"}]),
            ToolMessage(content="dir result", tool_call_id="tc1", name="list_dir"),
            AIMessage(content="intermediate thought"),
            ToolMessage(content="file content", tool_call_id="tc2", name="read_file"),
            AIMessage(content="final answer"),
        ],
        tool_history=["list_dir:{}", "read_file:{}"],
    )

    state = AgentState(messages=[])
    ticket = ExecutionTicket(ticket_type="task", topic="test")

    result = process_worker_result(
        node_name="Worker",
        state=state,
        engine_result=engine_result,
        execution_ticket=ticket,
        role_name="Explorer",
    )

    msgs = result.messages
    types = [type(m).__name__ for m in msgs]

    assert len(msgs) == 5, f"Expected 5 messages, got {len(msgs)}: {types}"
    assert types.count("ToolMessage") == 2, f"Expected 2 ToolMessages, got {types}"
    assert types.count("AIMessage") == 3, f"Expected 3 AIMessages, got {types}"

    # The last AIMessage should carry the summarised content
    assert isinstance(msgs[-1], AIMessage)
    assert "final answer" in msgs[-1].content or "Explorer" in msgs[-1].content


def test_process_worker_result_empty_messages():
    """Graceful handling when engine_result.messages is empty."""
    engine_result = EngineResult(messages=[])
    state = AgentState(messages=[])
    ticket = ExecutionTicket(ticket_type="task", topic="test")

    result = process_worker_result("Worker", state, engine_result, ticket, "Explorer")

    assert len(result.messages) == 1
    assert isinstance(result.messages[0], AIMessage)


def test_process_worker_result_no_trailing_ai():
    """When the last message is a ToolMessage, append a summary AIMessage."""
    engine_result = EngineResult(
        messages=[
            AIMessage(content=""),
            ToolMessage(content="data", tool_call_id="tc1", name="x"),
        ],
    )
    state = AgentState(messages=[])
    ticket = ExecutionTicket(ticket_type="task", topic="test")

    result = process_worker_result("Worker", state, engine_result, ticket, "Explorer")

    types = [type(m).__name__ for m in result.messages]
    assert types == ["AIMessage", "ToolMessage", "AIMessage"]


# ---------------------------------------------------------------------------
# 2. INTEGRATION TEST – WorkerNode._build_fallback_outcome
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_node_fallback_preserves_tool_messages():
    """
    WorkerNode._build_fallback_outcome calls process_worker_result.
    This test ensures the full node hook chain preserves ToolMessages.
    """
    from app.core.engine.nodes.worker import WorkerNode

    node = WorkerNode()

    # Minimal state so resolve_is_subtask works
    state = AgentState(messages=[])

    engine_result = EngineResult(
        messages=[
            AIMessage(content=""),
            ToolMessage(content="dir output", tool_call_id="tc1", name="list_dir"),
            AIMessage(content="answer"),
        ],
        tool_history=["list_dir:{}"],
    )

    result = await node._build_fallback_outcome(state, engine_result, {})

    types = [type(m).__name__ for m in (result.messages or [])]
    assert "ToolMessage" in types, f"WorkerNode dropped ToolMessages: {types}"
    assert len(result.messages) == 3, f"Expected 3 messages, got {len(result.messages)}: {types}"


# ---------------------------------------------------------------------------
# 3. E2E TEST – Full graph run writes ToolMessage into checkpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_checkpoint_contains_tool_messages():
    """
    Run a tiny graph with a mock Worker that emits ToolMessages,
    then inspect the checkpoint to verify they were persisted.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, StateGraph

    from app.core.engine.state import AgentState

    # In-memory SQLite for isolation
    conn = await aiosqlite.connect(":memory:")
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()

    # Build a minimal graph: mock_worker -> END
    async def mock_worker(state: AgentState, config):
        return StateUpdate(
            messages=[
                AIMessage(content=""),
                ToolMessage(content="fake tool result", tool_call_id="tc1", name="test_tool"),
                AIMessage(content="final"),
            ],
            next_node="__end__",
        )

    from app.core.engine.state.base import AgentState
    builder = StateGraph(AgentState)
    builder.add_node("worker", mock_worker)
    builder.set_entry_point("worker")
    builder.add_edge("worker", END)
    graph = builder.compile(checkpointer=saver)

    thread_id = "test-e2e-toolmsg"
    config = {"configurable": {"thread_id": thread_id}}

    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="hello")]),
        config=config,
    )

    # Read back the latest checkpoint
    cp = await saver.aget_tuple(config)
    assert cp is not None, "Checkpoint was not saved"

    msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])
    types = [type(m).__name__ for m in msgs]

    assert "ToolMessage" in types, (
        f"Checkpoint missing ToolMessage. Got {len(msgs)} messages: {types}"
    )

    await conn.close()


# ---------------------------------------------------------------------------
# 4. RETRY / RESUME TEST – Deserialization reconstructs ToolMessage history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_reconstructs_tool_message_history():
    """
    Simulate a retry/resume scenario:
      1. Run graph → checkpoint contains ToolMessages
      2. Load state from checkpoint (deserialization)
      3. Re-invoke graph with loaded state
      4. Assert full history (including ToolMessages) is preserved
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, StateGraph

    from app.core.engine.state.base import AgentState

    conn = await aiosqlite.connect(":memory:")
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()

    call_count = 0

    async def worker_with_tools(state: AgentState, config):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First run: emit AI → Tool → AI
            return StateUpdate(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "test_tool", "args": {}, "id": "tc1"}]),
                    ToolMessage(content="tool output line 1", tool_call_id="tc1", name="test_tool"),
                    AIMessage(content="analysis done"),
                ],
                next_node="__end__",
            )
        else:
            # Resume/retry: should see previous ToolMessage in state.messages
            return StateUpdate(
                messages=[AIMessage(content="retry ack")],
                next_node="__end__",
            )

    builder = StateGraph(AgentState)
    builder.add_node("worker", worker_with_tools)
    builder.set_entry_point("worker")
    builder.add_edge("worker", END)
    graph = builder.compile(checkpointer=saver)

    thread_id = "test-retry-toolmsg"
    config = {"configurable": {"thread_id": thread_id}}

    # --- First invocation ---
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="do it")]),
        config=config,
    )

    # Verify checkpoint contains ToolMessage after first run
    cp1 = await saver.aget_tuple(config)
    msgs1 = cp1.checkpoint.get("channel_values", {}).get("messages", [])
    types1 = [type(m).__name__ for m in msgs1]
    assert "ToolMessage" in types1, f"First run checkpoint missing ToolMessage: {types1}"

    # --- Simulate retry: re-invoke with the same thread_id ---
    # LangGraph loads previous checkpoint automatically
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="retry")]),
        config=config,
    )

    # Verify latest checkpoint STILL contains the original ToolMessage history
    cp2 = await saver.aget_tuple(config)
    msgs2 = cp2.checkpoint.get("channel_values", {}).get("messages", [])
    types2 = [type(m).__name__ for m in msgs2]

    assert "ToolMessage" in types2, (
        f"Retry/resume lost ToolMessage history. Got {len(msgs2)} messages: {types2}"
    )

    # Verify the ToolMessage content survived round-trip serialization
    tool_msgs = [m for m in msgs2 if isinstance(m, ToolMessage)]
    assert any("tool output line 1" in (m.content or "") for m in tool_msgs), (
        f"ToolMessage content corrupted or missing. Contents: {[m.content for m in tool_msgs]}"
    )

    await conn.close()


# ---------------------------------------------------------------------------
# 5. PRECISE ROLLBACK TEST – Checkpoint recovery is byte-for-byte exact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_precise_checkpoint_rollback():
    """
    Verify that checkpoint-based rollback reconstructs the EXACT state:
      1. Run a 3-step graph that accumulates ToolMessages
      2. Capture the checkpoint after step 2 (mid-state)
      3. Run step 3 → final state
      4. Rollback to mid-state checkpoint and compare message-by-message
      5. Assert ToolMessage count, content, order are identical
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, StateGraph

    from app.core.engine.state.base import AgentState

    conn = await aiosqlite.connect(":memory:")
    saver = AsyncSqliteSaver(conn=conn)
    await saver.setup()

    step_outputs: list[list[BaseMessage]] = []

    async def accumulating_worker(state: AgentState, config):
        step = len(step_outputs)
        if step == 0:
            msgs = [
                AIMessage(content="", tool_calls=[{"name": "tool_a", "args": {}, "id": "tc_a1"}]),
                ToolMessage(content="result A", tool_call_id="tc_a1", name="tool_a"),
                AIMessage(content="step 1 done"),
            ]
        elif step == 1:
            msgs = [
                AIMessage(content="", tool_calls=[{"name": "tool_b", "args": {}, "id": "tc_b1"}]),
                ToolMessage(content="result B", tool_call_id="tc_b1", name="tool_b"),
                AIMessage(content="step 2 done"),
            ]
        else:
            msgs = [AIMessage(content="step 3 done")]

        step_outputs.append(msgs)
        return StateUpdate(messages=msgs, next_node="__end__")

    builder = StateGraph(AgentState)
    builder.add_node("worker", accumulating_worker)
    builder.set_entry_point("worker")
    builder.add_edge("worker", END)
    graph = builder.compile(checkpointer=saver)

    thread_id = "test-rollback-exact"
    base_config = {"configurable": {"thread_id": thread_id}}

    # --- Step 1 & 2: run twice to accumulate history ---
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="start")]),
        config=base_config,
    )
    # Re-invoke to trigger step 2 (LangGraph resumes from last checkpoint)
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="continue")]),
        config=base_config,
    )

    # Get checkpoint after step 2
    cp_after_step2 = await saver.aget_tuple(base_config)
    assert cp_after_step2 is not None
    mid_checkpoint_id = cp_after_step2.checkpoint["id"]
    mid_state = cp_after_step2.checkpoint.get("channel_values", {}).get("messages", [])

    # Capture exact snapshot
    mid_snapshot = []
    for m in mid_state:
        mid_snapshot.append({
            "type": type(m).__name__,
            "content": str(m.content) if hasattr(m, "content") else "",
            "tool_call_id": getattr(m, "tool_call_id", None),
            "name": getattr(m, "name", None),
        })

    # --- Step 3: run to final state ---
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="finish")]),
        config=base_config,
    )

    # --- Rollback: re-invoke from mid-state checkpoint ---
    rollback_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": mid_checkpoint_id,
        }
    }
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="re-run from mid")]),
        config=rollback_config,
    )

    # Verify the state after rollback matches the mid-state snapshot
    cp_after_rollback = await saver.aget_tuple(rollback_config)
    assert cp_after_rollback is not None
    rollback_state = cp_after_rollback.checkpoint.get("channel_values", {}).get("messages", [])

    # Message count must match
    assert len(rollback_state) == len(mid_snapshot), (
        f"Rollback changed message count: {len(mid_snapshot)} -> {len(rollback_state)}"
    )

    # Message-by-message exact comparison
    for i, (orig, rolled) in enumerate(zip(mid_snapshot, rollback_state)):
        assert orig["type"] == type(rolled).__name__, (
            f"msg[{i}] type mismatch: {orig['type']} vs {type(rolled).__name__}"
        )
        assert orig["content"] == str(rolled.content), (
            f"msg[{i}] content mismatch: '{orig['content']}' vs '{rolled.content}'"
        )
        if orig["tool_call_id"]:
            assert orig["tool_call_id"] == getattr(rolled, "tool_call_id", None), (
                f"msg[{i}] tool_call_id mismatch"
            )
        if orig["name"]:
            assert orig["name"] == getattr(rolled, "name", None), (
                f"msg[{i}] name mismatch"
            )

    # ToolMessage count must survive rollback
    tool_count_mid = sum(1 for m in mid_state if isinstance(m, ToolMessage))
    tool_count_rb = sum(1 for m in rollback_state if isinstance(m, ToolMessage))
    assert tool_count_rb == tool_count_mid, (
        f"ToolMessage count changed after rollback: {tool_count_mid} -> {tool_count_rb}"
    )

    await conn.close()


if __name__ == "__main__":
    # Run without pytest to avoid import/rewrite issues in this env
    print("Running tests directly...")
    test_process_worker_result_preserves_tool_messages()
    print("✅ test_process_worker_result_preserves_tool_messages PASSED")
    test_process_worker_result_empty_messages()
    print("✅ test_process_worker_result_empty_messages PASSED")
    test_process_worker_result_no_trailing_ai()
    print("✅ test_process_worker_result_no_trailing_ai PASSED")
    asyncio.run(test_worker_node_fallback_preserves_tool_messages())
    print("✅ test_worker_node_fallback_preserves_tool_messages PASSED")
    asyncio.run(test_e2e_checkpoint_contains_tool_messages())
    print("✅ test_e2e_checkpoint_contains_tool_messages PASSED")
    asyncio.run(test_retry_reconstructs_tool_message_history())
    print("✅ test_retry_reconstructs_tool_message_history PASSED")
    asyncio.run(test_precise_checkpoint_rollback())
    print("✅ test_precise_checkpoint_rollback PASSED")
    print("\n🎉 All tests PASSED!")
