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

async def navigate_to_real_file_transfer():
    print("🚀 Target: Open REAL 'File Transfer Assistant' with Verification")
    
    # 1. Bring WeChat to front and get clean state
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(1)
    
    # Get bounds
    info_str = await desktop_control.ainvoke({"action": "get_active_app"})
    data = ast.literal_eval(info_str.replace("Active Application: ", ""))
    bounds_str = data.get("bounds")
    win_x, win_y, _, _ = map(int, bounds_str.split(","))

    # 2. Trigger Search (Cmd+F is usually search in WeChat)
    print("🔍 Triggering search...")
    await desktop_control.ainvoke({"action": "key_press", "key": "command+f"})
    await asyncio.sleep(0.5)
    
    # Clear and Type
    print("⌨️ Typing '文件传输助手'...")
    # Select all and delete to clear previous searches
    await desktop_control.ainvoke({"action": "key_press", "key": "command+a"})
    await desktop_control.ainvoke({"action": "key_press", "key": "delete"})
    await desktop_control.ainvoke({"action": "type_text", "text": "文件传输助手"})
    
    print("⏳ Waiting for robust results...")
    await asyncio.sleep(2)

    # 3. Identify THE Real One via OCR
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    target_pos = None
    try:
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        # Sort elements by Y coordinate (Top to bottom)
        candidates = [el for el in result.elements if "文件传输助手" == (el.text or "").strip()]
        
        if candidates:
            # Usually the first exact match in the search list is the "Feature" or "Contact" 
            # We skip anything too close to the top (maybe the search bar itself if it mirrored the text)
            filtered = [c for c in candidates if c.y > 60]
            if filtered:
                # Pick the top-most result that isn't the search bar
                best = filtered[0]
                target_pos = (win_x + best.x, win_y + best.y)
                print(f"🎯 Target identified at {target_pos} (Relative: {best.x}, {best.y})")
        
        if not target_pos:
            print("❌ Error: Could not distinguish the true '文件传输助手'.")
            return

        # 4. Click and VERIFY
        print(f"🖱️ Clicking and verifying...")
        await desktop_control.ainvoke({"action": "click", "x": target_pos[0], "y": target_pos[1]})
        await asyncio.sleep(1.5) # Wait for UI update
        
        # Check Window Title
        new_info_str = await desktop_control.ainvoke({"action": "get_active_app"})
        new_data = ast.literal_eval(new_info_str.replace("Active Application: ", ""))
        window_title = new_data.get("title", "")
        
        print(f"🖥️ Current Window Title: '{window_title}'")
        
        if "文件传输助手" in window_title:
            print("✅ VERIFICATION SUCCESS: Real 'File Transfer Assistant' is now open.")
            print("🏁 Navigation Complete!")
        else:
            print(f"⚠️ Verification Failed: Window title is '{window_title}', expected '文件传输助手'.")
            # Secondary check: Look for the title in the header area via OCR
            print("🔍 Performing secondary OCR verification of header...")
            # Capture the top header area
            header_region = f"{win_x},{win_y},1000,100"
            header_img = macos_driver.screenshot(region=header_region)
            h_result = await provider.process(task=VisionTask.OCR, image_source=header_img)
            if any("文件传输助手" in (el.text or "") for el in h_result.elements):
                print("✅ SECONDARY VERIFICATION SUCCESS: Header text confirmed.")
            else:
                print("❌ ABSOLUTE FAILURE: File Transfer Assistant not detected in header.")
            if os.path.exists(header_img): os.remove(header_img)

    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(navigate_to_real_file_transfer())
