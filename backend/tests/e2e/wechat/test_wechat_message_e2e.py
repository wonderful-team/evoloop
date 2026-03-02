
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
    print("🚀 LIVE E2E TEST: WECHAT MESSAGE FLOW")
    print("="*60)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    devs = adb_driver.list_devices()
    if not devs:
        print("❌ ERROR: No Android device connected.")
        return
    ctx.metadata["device_id"] = devs[0]["serial"]
    
    # 2. Prepare State
    user_input = "打开微信，帮我给‘文件传输助手’发一条消息，内容是：‘这是一条来自 EvoLoop 移动端 Reactor 的自动化测试消息’"
    
    execution_ticket = {
        "topic": "WeChat Messaging",
        "agent_config": {
            "role_name": "MobileSpecialist",
            "system_instructions": "You are a mobile automation expert. Use the Mobile Protocol to navigate WeChat. If you see icons but no text, use your spatial prior knowledge."
        },
        "acceptance_criteria": ["Message sent to 文件传输助手"]
    }
    
    state = AgentState(
        messages=[HumanMessage(content=user_input)],
        execution_ticket=execution_ticket,
        scratchpad={}
    )

    # 3. Running the Agent (Full Loop)
    print(f"\n🤖 Command: {user_input}")
    print("\nStarting Agent Node... (This will involve multiple ReAct loops)")
    
    node = WorkerNode()
    
    try:
        # We increase max_steps to allow for the full flow: Open -> Search -> Type -> Send
        result = await node(state, config={
            "configurable": {
                "thread_id": "wechat_test_session",
                "max_steps": 15
            }
        })
        
        print("\n" + "="*60)
        print("📊 TEST EXECUTION SUMMARY")
        print("="*60)
        
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and msg.content:
                # Check for AIMessage (Agent thinking/final response)
                from langchain_core.messages import AIMessage
                if isinstance(msg, AIMessage):
                    print(f"\n[Agent]: {msg.content}")
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            print(f"🛠️  Calling Tool: {tc['name']} ({json.dumps(tc['args'], ensure_ascii=False)})")
    
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_wechat_message_flow())
