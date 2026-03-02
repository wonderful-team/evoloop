
import asyncio
import os
import sys
import time
import logging
import re

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.environment.mobile import mobile_control
from app.infrastructure.drivers.adb import adb_driver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Phase9Verification")

async def test_heuristic_click():
    devices = adb_driver.list_devices()
    if not devices or devices[0]["status"] != "device":
        print("❌ No active Android devices found. Please connect a device via ADB.")
        return
    
    dev_id = devices[0]["serial"]
    print(f"\n🚀 PHASE 9 VERIFICATION: HEURISTIC BLIND CLICK ON {dev_id}...")
    
    print("\n--- Phase 1: Preparation ---")
    try:
        print("👉 Opening WeChat...")
        await mobile_control.ainvoke({"action": "open_app", "text": "com.tencent.mm", "device_id": dev_id})
        print("⏳ Waiting 1.0s for initial settlement...")
        await asyncio.sleep(1.0)
    except Exception as e:
        print(f"⚠️ Launch Error: {e}")
        return

    print("\n--- Phase 2: OCR Perception (Wait 1s) ---")
    print("⏳ Waiting 1.0s more to perfectly match user request...")
    await asyncio.sleep(1.0)
    
    start_time = time.time()
    try:
        ocr_result = await mobile_control.ainvoke({
            "action": "screenshot", 
            "ocr": True, 
            "device_id": dev_id, 
            "on_android": True
        })
        print(ocr_result)
        duration = time.time() - start_time
        print(f"✅ OCR completed in {duration:.2f}s")
        
        # Heuristic Logic Start
        print("\n--- Phase 3: Agent-style Reasoning ---")
        lines = ocr_result.splitlines()
        found_key = False
        target_pos = None

        # 1. Look for explicit "Q" (Search Icon symbol)
        for line in lines:
            if '"Q"' in line:
                match = re.search(r'\((\d+),\s*(\d+)\)', line)
                if match:
                    x, y = int(match.group(1)), int(match.group(2))
                    if x > 850 and y < 300:
                        print(f"🔍 [Perception] Found explicit 'Q' icon at ({x}, {y})")
                        target_pos = (x, y)
                        found_key = True
                        break
        
        # 2. Heuristic Fallback (Phase 9 Strategy)
        if not found_key:
            print("⚠️ [Heuristic] OCR failed to detect 'Q' or 'Search'.")
            print("🧠 [Heuristic] Applying Spatial Prior (Top-Right)...")
            # WeChat Search icon is almost always around (921, 162) on 1080p
            target_pos = (921, 162) 
            print(f"📍 [Heuristic] Strategy: Clicking 'Blind Spot' at {target_pos}")
        
        # 3. Action
        print(f"👉 Executing CLICK at {target_pos}...")
        await mobile_control.ainvoke({
            "action": "tap", 
            "x": target_pos[0], 
            "y": target_pos[1], 
            "device_id": dev_id
        })
        
        print("⏳ Waiting 2.0s for Search UI to open...")
        await asyncio.sleep(2.0)
        
        # 4. Final Verification
        print("\n--- Phase 4: Verification ---")
        verify_ocr = await mobile_control.ainvoke({
            "action": "screenshot", 
            "ocr": True, 
            "device_id": dev_id, 
            "on_android": True
        })
        
        if "搜索" in verify_ocr or "Search" in verify_ocr:
            print("✅ SUCCESS: Search bar is visible! Blind click worked.")
        else:
            print("❌ FAILURE: Search UI still not detected. Current screen top-bar:")
            for line in verify_ocr.splitlines()[:10]:
                print(f"  {line}")

    except Exception as e:
        print(f"❌ Error during verification: {e}")

if __name__ == "__main__":
    asyncio.run(test_heuristic_click())
