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

async def dump_wechat_absolute_ui():
    print("🚀 Starting Detailed WeChat UI Coordinate Dump (Absolute & Relative)...")
    
    # 1. Bring WeChat to front and get bounds
    print("Focusing WeChat...")
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(2)
    
    info_str = await desktop_control.ainvoke({"action": "get_active_app"})
    try:
        data = ast.literal_eval(info_str.replace("Active Application: ", ""))
        bounds_str = data.get("bounds")
        if not bounds_str:
            print("❌ Error: WeChat window bounds not found.")
            return
        # Parse x,y,w,h
        win_x, win_y, win_w, win_h = map(int, bounds_str.split(","))
    except Exception as e:
        print(f"❌ Error parsing app info: {e}")
        return
        
    print(f"📐 Window Top-Left Corner: ({win_x}, {win_y})")
    
    # 2. Take focused screenshot
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    try:
        # 3. Process with OCR
        print("🧠 Scanning for UI elements...")
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        if result.success:
            print(f"\n✅ Found {len(result.elements)} UI elements. Coordinates relative to Screen:\n")
            
            # Print Header
            header = f"{'ID':<4} | {'Text':<25} | {'Rel (X,Y)':<12} | {'Abs (X,Y)':<12} | {'Size (WxH)':<10}"
            print(header)
            print("-" * len(header))
            
            # Print Elements
            for el in result.elements:
                clean_text = (el.text or "").replace("\n", " ").strip()
                if len(clean_text) > 25:
                    clean_text = clean_text[:22] + "..."
                
                abs_x = win_x + el.x
                abs_y = win_y + el.y
                
                rel_pos = f"({el.x},{el.y})"
                abs_pos = f"({abs_x},{abs_y})"
                size = f"{el.width}x{el.height}"
                
                print(f"{el.id:<4} | {clean_text:<25} | {rel_pos:<12} | {abs_pos:<12} | {size:<10}")
                
            print(f"\n✨ Total Elements: {len(result.elements)}")
            print(f"💡 Rel (X,Y) = Offset from Window Top-Left")
            print(f"💡 Abs (X,Y) = Actual Screen Coordinates (Ready for Clicking)")
        else:
            print(f"❌ OCR processing failed.")
            
    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(dump_wechat_absolute_ui())
