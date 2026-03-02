
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
logger = logging.getLogger("RobustnessV4")

async def test_robustness():
    # Access the underlying function's file path
    try:
        source_file = mobile_control.func.__globals__['__file__']
        print(f"DEBUG: mobile_control source: {source_file}")
    except:
        print("DEBUG: Could not determine mobile_control source file")
    devices = adb_driver.list_devices()
    if not devices:
        print("No devices found")
        return
    dev = devices[0]["serial"]
    print(f"\n🚀 STARTING PHASE 4 ROBUSTNESS VERIFICATION ON {dev}...")
    
    # --- TEST 1: Activity Sentinel (Drift Recovery) ---
    print("\n[TEST 1] Activity Sentinel: Drift to Home and Auto-Recover")
    
    # 1. Open Settings
    await mobile_control.coroutine(action="open_app", text="com.android.settings", device_id=dev)
    await asyncio.sleep(2)
    
    # 2. Start a long-polling search in Settings
    print("⏳ Reactor: Looking for 'WLAN' (polling for 10s)...")
    # We'll use a task so we can trigger drift concurrently
    search_task = asyncio.create_task(
        mobile_control.coroutine(action="click", element_name="WLAN", timeout=12.0, device_id=dev)
    )
    
    # 3. Trigger Drift manually after 2 seconds
    await asyncio.sleep(3)
    print("⚠️  DRIFT TRIGGERED: Forcing Home Screen...")
    adb_driver.press_key("home", device_id=dev)
    
    # 4. Wait for Sentinel to detect and recover
    start = time.time()
    res = await search_task
    duration = time.time() - start
    
    print(f"✅ Sentinel Result: {res}")
    print(f"⏱  Total Recovery/Action Time: {duration:.2f}s")
    
    # --- TEST 2: Post-Action Verification & Recapture ---
    print("\n[TEST 2] Post-Action Verification: Detecting Unexpected App Jump")
    # This is harder to automate perfectly without a real ad, but we can simulate
    # by clicking something that we know shouldn't jump, and then forcing a jump.
    # Actually, intent_flow has the validate_outcome check.
    
    intents = [
        {"action": "click", "target": "WLAN"}
    ]
    # We'll manually jump right after the click happens (simulated via log monitoring)
    # But for a script, let's just see if it handles the 'intent_flow' logic.
    print("⏳ Executing Intent Flow with Sentinel...")
    res = await mobile_control.coroutine(action="intent_flow", intents=intents, device_id=dev)
    print(f"✅ Intent Flow Result: {res}")

if __name__ == "__main__":
    asyncio.run(test_robustness())
