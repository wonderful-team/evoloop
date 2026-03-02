
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
logger = logging.getLogger("CompareWeChatPerception")

async def run_perception_test():
    devices = adb_driver.list_devices()
    if not devices or devices[0]["status"] != "device":
        print("❌ No active Android devices found. Please connect a device via ADB.")
        return
    
    dev_id = devices[0]["serial"]
    print(f"\n🚀 WECHAT PERCEPTION TEST (1s WAIT) ON {dev_id}...")
    
    print("\n--- Phase 1: Launch & Wait ---")
    try:
        print("👉 Opening WeChat...")
        await mobile_control.ainvoke({"action": "open_app", "text": "com.tencent.mm", "device_id": dev_id})
        
        print("⏳ Waiting exactly 1.0s for UI to settle...")
        await asyncio.sleep(2.0) 
    except Exception as e:
        print(f"⚠️ Launch Error: {e}")
        return

    print("\n--- Phase 2: Capture & OCR ---")
    start_time = time.time()
    try:
        # Get OCR with explicit platform flag
        ocr_result = await mobile_control.ainvoke({
            "action": "screenshot", 
            "ocr": True, 
            "device_id": dev_id, 
            "on_android": True
        })
        duration = time.time() - start_time
        
        print(f"✅ OCR completed in {duration:.2f}s")
        print("\n--- Phase 3: OCR Results ---")
        print(ocr_result)
        
        # Heuristic check for search icon
        lines = ocr_result.splitlines()
        found_q = False
        for line in lines:
            if '"Q"' in line:
                match = re.search(r'\((\d+),\s*(\d+)\)', line)
                if match:
                    x, y = int(match.group(1)), int(match.group(2))
                    if x > 850 and y < 350:
                        print(f"\n🎯 FOUND Search Icon ('Q') at ({x}, {y})")
                        found_q = True
                        break
        
        if not found_q:
            print("\n⚠️ Search Icon ('Q') not detected in top-right area.")

    except Exception as e:
        print(f"❌ OCR Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_perception_test())
