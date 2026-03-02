
import asyncio
import os
import sys
import time
import logging

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.environment.mobile import mobile_control
from app.infrastructure.drivers.adb import adb_driver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VerifySilkinessV3")

async def test_mainline_reactor():
    devices = adb_driver.list_devices()
    if not devices:
        print("No devices found")
        return
    
    dev = devices[0]["serial"]
    print(f"\n🚀 VERIFYING MAINLINE REACTOR ON {dev}...")
    
    # Pre-test: Back to home
    adb_driver.press_key("home", device_id=dev)
    await asyncio.sleep(1)
    
    # Test Case 1: Atomic Reactor Click (Poll until appears)
    print("\n--- TEST 1: Atomic Reactor Click (Settings Navigation) ---")
    start = time.time()
    # Try to click something in Settings that takes a bit to load or navigate
    await mobile_control.coroutine(action="open_app", text="com.android.settings", device_id=dev)
    
    # Use the new Reactor-powered mobile_control click
    res = await mobile_control.coroutine(action="click", element_name="显示", device_id=dev)
    print(f"Result: {res}")
    print(f"Time Taken: {time.time()-start:.2f}s")
    
    # Test Case 2: Intent Flow (Multi-step)
    print("\n--- TEST 2: Intent Flow (WeChat Search Mock) ---")
    start = time.time()
    intents = [
        {"action": "click", "target": "微信"},
        {"action": "click", "target": "搜索"},
        {"action": "input", "text": "SilkinessV3"}
    ]
    res = await mobile_control.coroutine(action="intent_flow", intents=intents, device_id=dev)
    print(f"Result: {res}")
    print(f"Time Taken: {time.time()-start:.2f}s")
    
    print("\n✅ Verification complete. Check logs for perception fallback triggers.")

if __name__ == "__main__":
    asyncio.run(test_mainline_reactor())
