import asyncio
import os
import logging
import ast
from app.domain.tools.environment.desktop import desktop_control
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def batch_click_wechat_ui():
    print("🚀 Starting Batch UI Click Test for WeChat...")
    
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
        
    # 2. Capture and Scan
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    try:
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        if not result.success or not result.elements:
            print("❌ No elements found to click.")
            return

        print(f"✅ Found {len(result.elements)} elements. Preparing batch click...")
        
        # 3. Prepare Batch Actions
        batch_actions = []
        for el in result.elements:
            abs_x = win_x + el.x
            abs_y = win_y + el.y
            
            # Add a click action for each element
            batch_actions.append({
                "action": "click",
                "x": abs_x,
                "y": abs_y
            })
            
        print(f"🖱️ Executing {len(batch_actions)} clicks in sequence with 200ms delay...")
        
        # 4. Use the new 'batch' action in desktop_control
        batch_result = await desktop_control.ainvoke({
            "action": "batch",
            "actions": batch_actions,
            "delay_ms": 200,
            "continue_on_error": True
        })
        
        print(f"\n🏁 Batch Result:\n{batch_result}")
        
    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(batch_click_wechat_ui())
