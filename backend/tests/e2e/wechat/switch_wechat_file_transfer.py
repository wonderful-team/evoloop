import asyncio
import os
import logging
import ast
import time
from app.domain.tools.environment.desktop import desktop_control
from app.infrastructure.drivers.macos import macos_driver
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def switch_to_existing_file_transfer():
    print("🚀 Target: Switch to EXISTING 'File Transfer Assistant' conversation")
    
    # 1. Bring WeChat to front
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(1)
    
    # Get bounds
    info_str = await desktop_control.ainvoke({"action": "get_active_app"})
    data = ast.literal_eval(info_str.replace("Active Application: ", ""))
    bounds_str = data.get("bounds")
    win_x, win_y, _, _ = map(int, bounds_str.split(","))

    # 2. Perform focused scan of the sidebar/recent list area
    # Usually the sidebar is on the left. Let's scan the whole window or focus on the left ~350px.
    print("🧠 Scanning for '文件传输助手' in the current chat list...")
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    target_pos = None
    try:
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        # Look for the exact match in the sidebar area
        for el in result.elements:
            # We look for "文件传输助手" and typically sidebar items have smaller width/x than the main chat area
            if "文件传输助手" in (el.text or ""):
                # In WeChat Mac, sidebar list usually starts from x=70. Let's just find the first match.
                target_pos = (win_x + el.x, win_y + el.y)
                print(f"✅ Found in list at {target_pos} (Text: '{el.text}')")
                break
        
        if not target_pos:
            print("❌ Error: '文件传输助手' not found in the current chat list sidebar.")
            print("💡 Observation: Please ensure the conversation is visible in the sidebar for this test.")
            return

        # 3. Click to switch
        print(f"🖱️ Clicking to switch to conversation...")
        await desktop_control.ainvoke({"action": "click", "x": target_pos[0], "y": target_pos[1]})
        await asyncio.sleep(1) 

        # 4. Verify Header
        print("🔍 Verifying chat header...")
        # Capture the header area to confirm we are in the right chat
        header_region = f"{win_x},{win_y},1000,100"
        header_img = macos_driver.screenshot(region=header_region)
        h_result = await provider.process(task=VisionTask.OCR, image_source=header_img)
        
        found_header = any("文件传输助手" in (el.text or "") for el in h_result.elements)
        
        if found_header:
            print("✅ SUCCESS: Switched to 'File Transfer Assistant' conversation.")
            print("🏁 Navigation Complete!")
        else:
            print("❌ VERIFICATION FAILED: Did not detect '文件传输助手' in the chat header after clicking.")
            
        if os.path.exists(header_img): os.remove(header_img)

    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(switch_to_existing_file_transfer())
