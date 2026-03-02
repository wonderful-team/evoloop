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
logger = logging.getLogger("WeChatVisionFallbackTest")

async def test_vision_fallback():
    print("\n" + "="*60)
    print("🚀 LIVE TEST: VISION ANALYTICS FALLBACK (BLANK INPUT BOX)")
    print("="*60)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    devs = adb_driver.list_devices()
    if not devs:
        print("❌ ERROR: No Android device connected.")
        return
    ctx.metadata["device_id"] = devs[0]["serial"]
    
    # 2. Prepare State (Assume user is already in the file transfer chat)
    user_input = "我已经帮你打开了微信的‘文件传输助手’聊天界面。请帮我发送一条测试消息，内容是：‘Vision Fallback Test Successful’。注意：如果你找不到文本输入框，请使用 Vision Analytics 回退机制来寻找它。"
    
    execution_ticket = {
        "topic": "WeChat Message Sending (Direct)",
        "agent_config": {
            "role_name": "MobileSpecialist",
            "system_instructions": "You are a mobile automation expert. Use the Mobile Protocol. Use analyze_image specifically to find exact coordinates for empty text inputs if dump_ui or OCR returns nothing."
        },
        "tools_used": ["mobile_control", "analyze_image"],
        "acceptance_criteria": ["Message sent successfully within the current chat window"]
    }
    
    state = AgentState(
        messages=[HumanMessage(content=user_input)],
        execution_ticket=execution_ticket,
        scratchpad={}
    )

    # 3. Running the Agent
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

        result = await node(state, config={
            "configurable": {
                "thread_id": "wechat_vision_test",
                "max_steps": 10
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
    asyncio.run(test_vision_fallback())
