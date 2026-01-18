import asyncio
import os
import sys

from langchain_core.messages import HumanMessage

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.engine.graph_builder import GraphBuilder


async def run_meta_agent():
    print("--- [Meta Agent] Initialization ---")

    # 1. Build the Supervisor Graph
    # Assuming config is at app/core/engine/config/agent_main.yaml
    config_path = os.path.join(backend_dir, "app/core/engine/config/agent_main.yaml")

    if not os.path.exists(config_path):
        print(f"Error: Config not found at {config_path}")
        return

    builder = GraphBuilder()
    agent_graph = builder.build(config_path)

    print("--- [Meta Agent] Graph Built Successfully ---")

    # 2. Define the Prompt (Self-Evolution Task)
    prompt = """
    **MISSION: SELF-EVOLUTION**
    
    Objective: Implement a new component for yourself: `MemorySummarizer`.
    
    **Requirements**:
    1. Create a new file: `app/core/memory/summarizer.py`
    2. Implement a class `MemorySummarizer` with a method `async def summarize(self, text: str) -> str`.
    3. Use `LLMFactory.create_llm()` to generate a concise summary of the input text.
    4. Ensure it handles exceptions gracefully.
    
    **Constraints**:
    - Use `manage_file` to create the file.
    - Check if the file exists using `run_command` (ls -la) first.
    - DO NOT ask for human permission. Proceed autonomously until "finish".
    """

    inputs = {
        "messages": [HumanMessage(content=prompt)],
        "project_id": 1,
        "iteration_count": 0
    }

    config = {"recursion_limit": 50, "configurable": {"thread_id": "meta_agent_run_1"}}

    print(f"--- [Meta Agent] Starting Execution ---\nPrompt: {prompt.strip()}\n")

    # 3. Stream Execution
    async for event in agent_graph.astream(inputs, config=config):
        for node_name, result in event.items():
            print(f"--- Node Finished: {node_name} ---")
            if "messages" in result and result["messages"]:
                last_msg = result["messages"][-1]
                content = last_msg.content
                print(f"[{node_name}] Output: {content[:300]}..." if len(str(content)) > 300 else f"[{node_name}] Output: {content}")

                # Detecting if DiffTracker was triggered (via log check simulation)
                if "[Version Control]" in str(content):
                    print("✅ [DiffTracker] detected changes and injected diff!")
                if "[Pruned Tool Output]" in str(content):
                    print("✅ [ContextPruner] pruned old tool context!")

    print("--- [Meta Agent] Execution Finished ---")


if __name__ == "__main__":
    asyncio.run(run_meta_agent())
