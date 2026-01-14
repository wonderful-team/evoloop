import os
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.memory.pruner import ContextPruner


def test_pruner():
    print("--- Test: Context Pruner ---")

    # 1. Create a "fat" history
    # 5 tool calls with LARGE outputs
    large_output = "X" * 10000 # 10k chars

    messages = [
        HumanMessage(content="Start"),
        AIMessage(content="Step 1", tool_calls=[{"name": "test", "args": {}, "id": "1"}]),
        ToolMessage(content=large_output, tool_call_id="1", name="test"), # Should be pruned

        AIMessage(content="Step 2", tool_calls=[{"name": "test", "args": {}, "id": "2"}]),
        ToolMessage(content=large_output, tool_call_id="2", name="test"), # Should be pruned

        AIMessage(content="Step 3", tool_calls=[{"name": "test", "args": {}, "id": "3"}]),
        ToolMessage(content=large_output, tool_call_id="3", name="test"), # Should be pruned

        # Recent turn (Protected)
        HumanMessage(content="What did I just do?"),
        AIMessage(content="You ran tests.", tool_calls=[{"name": "test", "args": {}, "id": "4"}]),
        ToolMessage(content=large_output, tool_call_id="4", name="test"), # Recent, might be protected?
    ]

    # Calculate proxy token usage
    initial_usage = ContextPruner.get_token_usage_proxy(messages)
    print(f"Initial Usage (approx tokens): {initial_usage}")
    print(f"Total Chars: {sum(len(m.content) for m in messages)}")

    # 2. Prune
    # Note: PRUNE_PROTECT_TOKENS set to 30000 chars in implementation
    # Total here is > 40k chars.
    pruned = ContextPruner.prune_messages(messages)

    final_usage = ContextPruner.get_token_usage_proxy(pruned)
    print(f"Final Usage (approx tokens): {final_usage}")
    print(f"Total Chars: {sum(len(m.content) for m in pruned)}")

    # 3. Verify
    pruned_count = 0
    for i, msg in enumerate(pruned):
        if "[Pruned Tool Output" in str(msg.content):
            print(f"Message {i} WAS PRUNED.")
            pruned_count += 1
        else:
            # print(f"Message {i} kept.")
            pass

    if pruned_count > 0:
        print(f"SUCCESS: Pruned {pruned_count} messages.")
    else:
        print("FAIL: No messages pruned. Limit might be too high for this test.")

if __name__ == "__main__":
    test_pruner()
