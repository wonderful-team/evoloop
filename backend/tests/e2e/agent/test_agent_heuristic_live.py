
import asyncio
import os
import sys
import logging
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.state import AgentState
from app.core.context import ContextManager
from app.infrastructure.drivers.adb import adb_driver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("RealAgentTest")

async def test_live_agent_heuristic():
    print("\n" + "="*60)
    print("🤖 REAL AGENT VERIFICATION: PHASE 9 HEURISTIC (TARGETED)")
    print("="*60)

    # 1. Setup Context (Crucial for prompt building)
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    # Check for real device
    devs = adb_driver.list_devices()
    if devs:
        ctx.metadata["device_id"] = devs[0]["serial"]
    else:
        ctx.metadata["device_id"] = "MOCK_DEVICE"
    
    # 2. Prepare State & Ticket
    execution_ticket = {
        "topic": "在微信中搜索'文件传输助手'",
        "agent_config": {
            "role_name": "MobileSpecialist",
            "system_instructions": "You are a mobile automation expert. Use the Mobile Protocol to navigate WeChat."
        },
        "acceptance_criteria": ["进入搜索界面", "找到文件传输助手"]
    }
    
    state = AgentState(
        messages=[HumanMessage(content="请帮我在微信中搜索'文件传输助手'")],
        execution_ticket=execution_ticket,
        scratchpad={}
    )

    # 3. Simulate "Adverse Condition" (Missing Q)
    print("\n--- Injecting 'Search Icon Missing' Scenario into Memory ---")
    mock_ocr_result = """
### OCR Results (Detected Text & Coordinates):
[0] "2:15" (93, 55) [text]
[1] "微信" (539, 160) [text]
[2] "Mac 微信已登录" (291, 274) [text]
[3] "好了，已发" (249, 444) [text]
[4] "文件传输助手" (266, 611) [text]
[5] "下午2:04" (991, 2310) [text]
(Note: The top-right area contains a search icon, but it is NOT detected in this OCR pass.)
"""
    
    # Pre-add the history: "Screenshot taken, result below"
    state["messages"].append(AIMessage(content="I have opened WeChat. taking a screenshot to find the search button.", tool_calls=[{
        "name": "mobile_control",
        "args": {"action": "screenshot", "ocr": True},
        "id": "call_perception_1"
    }]))
    state["messages"].append(ToolMessage(content=mock_ocr_result, tool_call_id="call_perception_1"))

    # 4. Invoke Worker Node
    print("\n🚀 Invoking Worker Node logic...")
    node = WorkerNode()
    
    # We run the node. It will call the LLM and wait for its response.
    # We want to see if the VERY NEXT message from the LLM is a Blind Click.
    result = await node(state, config={"configurable": {"thread_id": "real_agent_test"}})
    
    # 5. Analysis
    print("\n" + "="*60)
    print("📊 AGENT DECISION ANALYSIS")
    print("="*60)
    
    found_decision = False
    for msg in result.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            found_decision = True
            print(f"\n🧠 Agent Reasoning: {msg.content}")
            for tc in msg.tool_calls:
                print(f"\n🛠️ ACTION: {tc['name']}")
                print(f"   ARGS: {json.dumps(tc['args'], ensure_ascii=False, indent=2)}")
                
                # Check for Blind Click (Top-Right Area)
                args = tc['args']
                if tc['name'] == 'mobile_control' and args.get('action') == 'tap':
                    x, y = args.get('x'), args.get('y')
                    if x and y and x > 850 and y < 350:
                        print("\n✅ SUCCESS: The Agent correctly decided to perform a 'Blind Click' on the top-right corner, following the Phase 9 Spatial Prior strategy!")
                    else:
                        print("\n❌ FAILED: The Agent clicked elsewhere.")
                elif 'element_name' in args and (args['element_name'] == 'Q' or args['element_name'] == '搜索'):
                    print("\n⚠️ Agent is still trying to find the missing label by name (Old behavior).")
    
    if not found_decision:
        print("\n❌ No terminal action found in the Agent response.")

if __name__ == "__main__":
    asyncio.run(test_live_agent_heuristic())
