
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
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("WeChatMessageTest")

async def test_wechat_message_flow():
    print("\n" + "="*60)
    print("🚀 LIVE E2E TEST: WECHAT MESSAGE FLOW (SEARCH-FIRST)")
    print("="*60)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    devs = adb_driver.list_devices()
    if not devs:
        print("❌ ERROR: No Android device connected.")
        return
    ctx.metadata["device_id"] = devs[0]["serial"]
    
    # 2. Prepare State (More explicit instruction to avoid being tricked by content)
    user_input = "打开微信，帮我给‘文件传输助手’发一条消息，内容是：‘这是一条来自 EvoLoop 移动端 Reactor 的自动化测试消息’。提示：为了准确找到它，请先点击右上角的搜索图标，然后输入名称进行搜索。"
    
    execution_ticket = {
        "topic": "WeChat Messaging (Search-Guided)",
        "agent_config": {
            "role_name": "MobileSpecialist",
            "system_instructions": "You are a mobile automation expert. Use the Mobile Protocol. Use the search icon (top-right) if standard text matching is ambiguous. If OCR is missing the search icon, remember the top-right heuristic. DO NOT attempt to use 'desktop_control'."
        },
        "tools_used": ["mobile_control", "analyze_image", "wait", "verify_ui_state"],
        "acceptance_criteria": ["Message sent to 文件传输助手 via Search"]
    }
    
    state = AgentState(
        messages=[HumanMessage(content=user_input)],
        execution_ticket=execution_ticket,
        scratchpad={}
    )

    # 3. Running the Agent (Full Loop)
    print(f"\n🤖 Command: {user_input}")
    
    node = WorkerNode()
    
    try:
        from app.core.tools.manager import tool_manager
        
        # Override the tool manager briefly to prevent desktop_control injection for this test
        original_get_tools = tool_manager.get_node_tools
        def mock_get_node_tools(role: str, state_override=None):
            tools = original_get_tools(role, state_override)
            return [t for t in tools if t.name != "desktop_control" and t.name != "browser_control"]
        tool_manager.get_node_tools = mock_get_node_tools

        # Increase max_steps to allow for navigation
        result = await node(state, config={
            "configurable": {
                "thread_id": "wechat_test_v2",
                "max_steps": 15
            }
        })
        
        # Restore mock
        tool_manager.get_node_tools = original_get_tools

        print("\n" + "="*60)
        print("📊 TEST EXECUTION SUMMARY")
        print("="*60)
        
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and msg.content:
                from langchain_core.messages import AIMessage
                if isinstance(msg, AIMessage):
                    print(f"\n[Agent]: {msg.content}")
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            print(f"🛠️  Calling Tool: {tc['name']} ({json.dumps(tc['args'], ensure_ascii=False)})")
    
    except Exception as e:
        print(f"❌ Execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_wechat_message_flow())
