import asyncio
import os
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.memory.pruner import ContextPruner
from app.domain.terminal.manager import terminal_manager


async def test_pruner():
    print("\n--- Test: Context Pruner (3 Turns) ---")

    large_output = "X" * 10000 # 10k chars

    # 3 Turns of history (Turn = Human + AI + Tool)
    messages = [
        # Turn 1
        HumanMessage(content="Turn 1"),
        AIMessage(content="Step 1", tool_calls=[{"name": "test", "args": {}, "id": "1"}]),
        ToolMessage(content=large_output, tool_call_id="1", name="test"),

        # Turn 2
        HumanMessage(content="Turn 2"),
        AIMessage(content="Step 2", tool_calls=[{"name": "test", "args": {}, "id": "2"}]),
        ToolMessage(content=large_output, tool_call_id="2", name="test"),

        # Turn 3 (Recent)
        HumanMessage(content="Turn 3"),
        AIMessage(content="Step 3", tool_calls=[{"name": "test", "args": {}, "id": "3"}]),
        ToolMessage(content=large_output, tool_call_id="3", name="test"),
    ]

    print(f"Total Chars: {sum(len(m.content) for m in messages)}")

    pruned = ContextPruner.prune_messages(messages)

    pruned_count = 0
    for i, msg in enumerate(pruned):
        if "[Pruned Tool Output" in str(msg.content):
            print(f"Message {i} (Tool) WAS PRUNED.")
            pruned_count += 1

    if pruned_count > 0:
        print(f"SUCCESS: Pruned {pruned_count} messages.")
    else:
        print("FAIL: No messages pruned.")

async def test_terminal():
    print("\n--- Test: Stateful Terminal ---")

    # 1. Check PWD
    out, err, code = terminal_manager.run_command("pwd")
    original_cwd = out.strip()
    print(f"Initial PWD: {original_cwd}")

    # 2. CD to parent
    terminal_manager.run_command("cd ..")
    out, err, code = terminal_manager.run_command("pwd")
    new_cwd = out.strip()
    print(f"New PWD: {new_cwd}")

    if new_cwd != original_cwd and new_cwd in original_cwd:
        print("SUCCESS: cd command worked (State maintained).")
    else:
        print("FAIL: cd command did not persist state.")

    # 3. Export Env
    terminal_manager.run_command("export MY_VAR='Hello EvoLoop'")
    out, err, code = terminal_manager.run_command("echo $MY_VAR")
    echo_out = out.strip()
    print(f"Echo Output: {echo_out}")

    if "Hello EvoLoop" in echo_out:
        print("SUCCESS: export command worked (Env maintained).")
    else:
        print("FAIL: export command did not persist.")

async def main():
    await test_pruner()
    await test_terminal()

if __name__ == "__main__":
    asyncio.run(main())
