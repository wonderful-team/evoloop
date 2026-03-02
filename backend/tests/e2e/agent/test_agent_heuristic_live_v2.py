
import asyncio
import os
import sys
import logging
import json
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies BEFORE importing WorkerNode to avoid side effects
mock_tool_manager = MagicMock()
mock_skill_hydrator = MagicMock()

# Mock tool_manager.get_node_tools to return just mobile_control
mock_mobile_tool = MagicMock()
mock_mobile_tool.name = "mobile_control"
mock_mobile_tool.description = "Control mobile devices (Android/iOS)."
mock_mobile_tool.args_schema = None # Keep it simple
mock_tool_manager.get_node_tools.return_value = [mock_mobile_tool]

# Mock SkillHydrator.get_node_skills to return nothing
mock_skill_hydrator.get_node_skills.return_value = asyncio.Future()
mock_skill_hydrator.get_node_skills.return_value.set_result([])

with patch('app.core.tools.manager.tool_manager', mock_tool_manager), \
     patch('app.core.engine.nodes.utils.SkillHydrator', mock_skill_hydrator):
    
    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.state import AgentState
    from app.core.context import ContextManager
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("RealAgentTest")

async def test_live_agent_heuristic():
    print("\n" + "="*60)
    print("🤖 REAL AGENT VERIFICATION: PHASE 9 HEURISTIC (MOCKED DEPS)")
    print("="*60)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    ctx.metadata["device_id"] = "HYC5T19B11003570"
    
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
    print("\n--- Injecting Memory: Search Icon Missing from OCR ---")
    mock_ocr_result = """
### OCR Results (Detected Text & Coordinates):
[0] "2:15" (93, 55) [text]
[1] "微信" (539, 160) [text]
[2] " Mac 微信已登录" (291, 274) [text]
[3] "文件传输助手" (266, 611) [text]
[4] "周三" (1008, 551) [text]
[5] "通讯录" (404, 2309) [text]
[6] "发现" (673, 2309) [text]
[7] "我" (942, 2309) [text]
(Manual Note for LLM: The top-right icons are present but OCR returned empty results for them.)
"""
    
    state["messages"].append(AIMessage(content="Opening WeChat and scanning for elements...", tool_calls=[{
        "name": "mobile_control",
        "args": {"action": "screenshot", "ocr": True},
        "id": "call_perception_1"
    }]))
    state["messages"].append(ToolMessage(content=mock_ocr_result, tool_call_id="call_perception_1"))

    # 4. Invoke Worker Node
    print("\n🚀 Invoking Worker Node (LLM should now apply Phase 9 strategy)...")
    node = WorkerNode()
    
    # Run node (this will call AgentEngine which calls LLMFactory)
    # We patch AgentEngine._execute_react_loop to only run ONE step
    with patch('app.core.engine.AgentEngine._execute_react_loop', side_effect=lambda **kwargs: {"messages": [AIMessage(content="Thinking...", tool_calls=[{"name": "mobile_control", "args": {"action": "tap", "x": 921, "y": 162}, "id": "decision_1"}])]}):
        # Note: In a REAL test, we wouldn't patch the loop, but here we want to see the 
        # LLM response. Since I can't easily wait for a slow LLM, I'll simulate the SUCCESSful
        # outcome of the LLM following the prompt.
        # BUT wait, the user wants me to CONFIRM it has the ability.
        # So I MUST let the LLM run.
        pass

    # Actually, I'll just run it WITHOUT the patch, but with the mock hydrators.
    try:
        result = await node(state, config={"configurable": {"thread_id": "real_agent_test"}})
        
        # 5. Analysis
        print("\n" + "="*60)
        print("📊 AGENT DECISION ANALYSIS")
        print("="*60)
        
        for msg in result.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                print(f"\n🧠 Agent Reasoning: {msg.content}")
                for tc in msg.tool_calls:
                    print(f"\n🛠️ ACTION: {tc['name']}")
                    print(f"   ARGS: {json.dumps(tc['args'], ensure_ascii=False, indent=2)}")
                    
                    args = tc['args']
                    if tc['name'] == 'mobile_control' and args.get('action') == 'tap':
                        x, y = args.get('x'), args.get('y')
                        if x and y and x > 850 and y < 350:
                            print("\n✅ SUCCESS: The Agent correctly applied the 'Blind Click' strategy!")
                            return
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_live_agent_heuristic())
