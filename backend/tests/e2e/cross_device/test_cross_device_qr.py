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
logger = logging.getLogger("CrossDeviceQRTest")

async def test_cross_device_qr():
    print("\n" + "="*80)
    print("🚀 LIVE TEST: CROSS-DEVICE QR AUTHENTICATION (HUMAN-IN-THE-LOOP)")
    print("="*80)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    devs = adb_driver.list_devices()
    if not devs:
        print("❌ ERROR: No Android device connected.")
        return
    ctx.metadata["device_id"] = devs[0]["serial"]
    
    # 2. Prepare State
    # Simulate a scenario where the PC is showing a QR code and needs phone authorization.
    user_input = "我已经把电脑端的微信/网页登陆二维码打开了，并且把手机放在支架上对准了屏幕。请你操作测试机打开微信的“扫一扫”功能，耐心等待（不断截图刷新）直到物理扫码成功跳转到确认识别页面，然后帮我点击绿色的“登录/同意”按钮完成授权！"
    
    execution_ticket = {
        "topic": "Human-in-the-Loop QR Scan Auth",
        "agent_config": {
            "role_name": "MultiDeviceSpecialist",
            "system_instructions": "You are a mobile automation expert conducting a human-in-the-loop physical test. Step 1: Open WeChat (com.tencent.mm). Step 2: Use Heuristic UI logic (e.g. blind click top right '+') to open the 'Scan' (扫一扫) feature. Step 3: Enter a visual polling loop (repeatedly capturing screenshots) until the screen changes to the login authorization page. Step 4: Click the prominent green 'Login' or 'Agree' button to confirm."
        },
        "tools_used": ["mobile_control", "analyze_image"],
        "acceptance_criteria": ["Successfully navigates to WeChat Camera Scan UI", "Detects authorization page transition", "Clicks authorization button"]
    }
    
    state = AgentState(
        messages=[HumanMessage(content=user_input)],
        execution_ticket=execution_ticket,
        scratchpad={}
    )

    # 3. Running the Agent
    print(f"\n🤖 Command: {user_input}")
    print("\n⚠️  [HUMAN REQUIRED]: Please ensure your phone camera is physically pointing at a valid login QR code before the agent reaches Step 3.\n")
    
    node = WorkerNode()
    
    try:
        result = await node(state, config={
            "configurable": {
                "thread_id": "cross_device_qr_test",
                "max_steps": 15 # Give it more steps for polling
            }
        })

        print("\n" + "="*80)
        print("📊 TEST EXECUTION SUMMARY")
        print("="*80)
        
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
    asyncio.run(test_cross_device_qr())
