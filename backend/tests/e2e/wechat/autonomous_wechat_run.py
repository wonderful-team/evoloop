import asyncio
import os
import logging
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.state import AgentState
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO)
# Set some specific loggers to debug to see the tool calls
logging.getLogger("app.core.engine").setLevel(logging.INFO)
logging.getLogger("app.core.tools").setLevel(logging.INFO)

async def run_autonomous_navigation_test():
    print("🚀 Starting Autonomous Mode Test (Integrated Architecture)...")
    
    # 1. Build the Unified Graph
    config_path = os.path.abspath("app/core/engine/config/agent_main.yaml")
    builder = GraphBuilder()
    graph = builder.build(config_path)
    
    # 2. Initialize State
    # Goal: Use the newly integrated spatial awareness to find and click "File Transfer Assistant"
    # without any hardcoded coordinates or scripts.
    initial_state: AgentState = {
        "messages": [
            HumanMessage(content="打开微信，切换到'文件传输助手'对话，并发送一条消息内容为：'[全自主模式] 系统集成验证：窗口感知与局部扫瞄已生效。'。操作完成后回复任务结果。")
        ],
        "project_id": 1,
        "iteration_count": 0,
        "scratchpad": {},
        "active_window": None
    }
    
    # 3. Execute Graph
    config = {"configurable": {"thread_id": "auto-test-001"}}
    
    print("\n--- 🧠 Agent Reasoning Start ---")
    async for event in graph.astream(initial_state, config=config, stream_mode="values"):
        if "next_node" in event:
            node = event.get("next_node")
            if node:
                print(f"\n➡️  Transitioning to: [{node}]")
        
        # We can also monitor the messages list for progress
        messages = event.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                for tc in last_msg.tool_calls:
                    print(f"🛠️  Tool Call: {tc['name']} (Args: {tc['args']})")
    
    print("\n--- ✅ Autonomous Test Complete ---")

if __name__ == "__main__":
    # Ensure environment vars are set
    os.environ["ENABLE_VISION_OCR"] = "1" 
    asyncio.run(run_autonomous_navigation_test())
