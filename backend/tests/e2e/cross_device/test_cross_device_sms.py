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
logger = logging.getLogger("CrossDeviceSMSTest")


async def test_cross_device_sms():
    print("\n" + "=" * 80)
    print("🚀 LIVE TEST: CROSS-DEVICE SMS AUTHENTICATION (MAC + ANDROID)")
    print("=" * 80)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True

    devs = adb_driver.list_devices()
    if not devs:
        print("❌ ERROR: No Android device connected.")
        return
    ctx.metadata["device_id"] = devs[0]["serial"]

    # 2. Prepare State
    # Simulate a scenario where the agent just clicked "Send SMS" on a Mac browser, and needs to fetch it from Android.
    user_input = "请用短信验证码的方式登录 https://www.kimi.com"

    execution_ticket = {
        "topic": "Cross-Device Verification Hub",
        "agent_config": {
            "role_name": "MultiDeviceSpecialist",
            "system_instructions": "You are a cross-device automation expert holding both a Mac and an Android phone. STRICTLY follow the Cross-Device Sync Protocol. Use the mobile_control `read_sms` action with a regex to get the verification code."
        },
        "tools_used": ["desktop_control", "mobile_control", "stash_to_clipboard"],
        "acceptance_criteria": [
            "SMS code is successfully read from the Android phone",
            "Code is saved to workspace clipboard via stash_to_clipboard"
        ]
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
        result = await node(state, config={
            "configurable": {
                "thread_id": "cross_device_sms_test",
                "max_steps": 10
            }
        })

        print("\n" + "=" * 80)
        print("📊 TEST EXECUTION SUMMARY")
        print("=" * 80)

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
    asyncio.run(test_cross_device_sms())
