
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
logger = logging.getLogger("CompareWeChatPerception")

async def compare_perception():
    devices = adb_driver.list_devices()
    if not devices or devices[0]["status"] != "device":
        print("❌ No active Android devices found. Please connect a device via ADB.")
        return
    
    dev_id = devices[0]["serial"]
    print(f"\n🚀 STARTING WECHAT PERCEPTION COMPARISON ON {dev_id}...")
    
    # 1. Ensure WeChat is in foreground
    print("\n--- Phase 1: Preparation (Opening WeChat) ---")
    try:
        await mobile_control.ainvoke({"action": "open_app", "text": "com.tencent.mm", "device_id": dev_id})
    except Exception as e:
        logger.warning(f"Failed to open WeChat: {e}. Assuming it's already open.")
    
    await asyncio.sleep(3) # Wait for app to settle
    
    # 2. Dump UI (A11y Hierarchy)
    print("\n--- Phase 2: Dump UI (A11y Hierarchy) ---")
    start_time = time.time()
    try:
        xml_result = await mobile_control.ainvoke({"action": "dump_ui", "device_id": dev_id})
        xml_duration = time.time() - start_time
        print(f"✅ XML Hierarchy Length: {len(xml_result)} characters")
        print(f"⏱️ Duration: {xml_duration:.2f}s")
    except Exception as e:
        print(f"❌ Dump UI failed: {e}")
        xml_result = ""
    
    # 3. OCR Recognition
    print("\n--- Phase 3: Vision OCR Recognition ---")
    start_time = time.time()
    try:
        # Get screenshot first
        screenshot_path = await mobile_control.ainvoke({"action": "screenshot", "ocr": False, "device_id": dev_id})
        print(f"📸 Screenshot saved to: {screenshot_path}")
        
        # Get OCR
        ocr_result = await mobile_control.ainvoke({"action": "screenshot", "ocr": True, "device_id": dev_id})
        ocr_duration = time.time() - start_time
        
        # Print first 20 lines (typically top bar)
        lines = ocr_result.splitlines()
        print(f"✅ OCR Recognition Result (Top 20 lines):")
        for line in lines[:20]:
            print(line)
        
        print(f"⏱️ Duration: {ocr_duration:.2f}s")
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        ocr_result = ""
    
    # 4. Keyword Analysis
    print("\n--- Phase 4: Comparative Analysis ---")
    # Common WeChat keywords in Chinese
    keywords = ["微信", "通讯录", "发现", "我", "搜索", "文件传输助手", "扫一扫"]
    
    print(f"{'Keyword':<15} | {'XML (A11y)':<12} | {'OCR (Vision)':<12}")
    print("-" * 45)
    for kw in keywords:
        in_xml = kw in xml_result
        in_ocr = kw in ocr_result
        xml_status = "✅ YES" if in_xml else "❌ NO"
        ocr_status = "✅ YES" if in_ocr else "❌ NO"
        print(f"{kw:<15} | {xml_status:<12} | {ocr_status:<12}")
        
    # 5. Search Exploration (Attempting to click "Q")
    print("\n--- Phase 5: Search Exploration (Interacting with 'Q' icon) ---")
    search_icon_pos = None
    for i, line in enumerate(lines):
        if '"Q"' in line and '(92' in line: # Likely the top-right search icon
            # Extract coordinates (921, 162)
            import re
            match = re.search(r'\((\d+),\s*(\d+)\)', line)
            if match:
                search_icon_pos = (int(match.group(1)), int(match.group(2)))
                print(f"🎯 Potential Search Icon found as 'Q' at {search_icon_pos}")
                break
    
    if search_icon_pos:
        print(f"👉 Clicking at {search_icon_pos} to open search bar...")
        await mobile_control.ainvoke({"action": "tap", "x": search_icon_pos[0], "y": search_icon_pos[1], "device_id": dev_id})
        await asyncio.sleep(2) # Wait for search bar to appear
        
        # Check again
        new_ocr = await mobile_control.ainvoke({"action": "screenshot", "ocr": True, "device_id": dev_id})
        if "搜索" in new_ocr:
            print("✅ SUCCESS: Search bar opened. '搜索' keyword is now visible!")
        else:
            print("❌ FAILURE: '搜索' still not found after click. OCR results:")
            print(new_ocr.splitlines()[:10])
    else:
        print("❓ No 'Q' icon found in top-right to test.")

    print("\n✅ Comparison and Exploration complete.")

if __name__ == "__main__":
    asyncio.run(compare_perception())
