import asyncio
import os
import logging
import ast
import time
from app.domain.tools.environment.desktop import desktop_control
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def navigate_to_file_transfer_assistant():
    print("🚀 Target: Open 'File Transfer Assistant' in WeChat")
    
    # 1. Bring WeChat to front and get bounds
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(2)
    
    info_str = await desktop_control.ainvoke({"action": "get_active_app"})
    try:
        data = ast.literal_eval(info_str.replace("Active Application: ", ""))
        bounds_str = data.get("bounds")
        if not bounds_str:
            print("❌ Error: WeChat window bounds not found.")
            return
        win_x, win_y, _, _ = map(int, bounds_str.split(","))
    except Exception as e:
        print(f"❌ Error parsing app info: {e}")
        return
    
    print(f"📐 Window focused at {win_x}, {win_y}")

    # 2. Find Search Box
    print("🔍 Looking for Search box...")
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    search_box_pos = None
    try:
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        # Look for "搜索", "Search", or a box at the top left
        for el in result.elements:
            text = (el.text or "").lower()
            if "搜索" in text or "search" in text or "搜案" in text: # "搜案" was previously seen in OCR
                search_box_pos = (win_x + el.x, win_y + el.y)
                print(f"✅ Found search box at {search_box_pos} (text: '{el.text}')")
                break
        
        if not search_box_pos:
            # Fallback if text recognition missed it but we know where it usually is (top left)
            print("⚠️ Search text not found, trying common coordinates...")
            search_box_pos = (win_x + 100, win_y + 35)
            
    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

    # 3. Click and Type
    print(f"⌨️ Clicking search and typing '文件传输助手'...")
    await desktop_control.ainvoke({
        "action": "batch",
        "actions": [
            {"action": "click", "x": search_box_pos[0], "y": search_box_pos[1]},
            {"action": "type_text", "text": "文件传输助手"}
        ],
        "delay_ms": 500
    })
    
    print("⏳ Waiting for search results to appear...")
    await asyncio.sleep(2)

    # 4. Find and click the result
    print("🎯 Identifying the 'File Transfer Assistant' result...")
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    target_pos = None
    try:
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        # We look for "文件传输助手" in the elements
        for el in result.elements:
            if "文件传输助手" in el.text:
                # Prioritize elements that are likely in the result list (below search bar)
                if el.y > 50: 
                    target_pos = (win_x + el.x, win_y + el.y)
                    print(f"✅ Found target result at {target_pos}")
                    break
        
        if target_pos:
            print(f"🖱️ Clicking 'File Transfer Assistant'...")
            await desktop_control.ainvoke({"action": "click", "x": target_pos[0], "y": target_pos[1]})
            print("🏁 Navigation Complete!")
        else:
            print("❌ Error: Could not find '文件传输助手' in search results.")
            
    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(navigate_to_file_transfer_assistant())
