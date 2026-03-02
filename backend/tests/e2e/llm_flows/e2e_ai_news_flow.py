import asyncio
import os
import logging
import ast
import time
import subprocess
from app.domain.tools.environment.desktop import desktop_control
from app.infrastructure.drivers.macos import macos_driver
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def e2e_ai_news_flow():
    print("🚀 Starting E2E Flow: Chrome AI News -> WeChat File Transfer")
    
    # --- PHASE 1: Chrome Search ---
    print("\n🌐 Step 1: Opening Chrome and searching for AI News...")
    await desktop_control.ainvoke({"action": "open_app", "app_name": "Google Chrome"})
    await asyncio.sleep(2)
    
    # Use Cmd+L to focus address bar and search
    print("📂 Searching for 'latest AI news today'...")
    await desktop_control.ainvoke({"action": "key_press", "key": "command+l"})
    await asyncio.sleep(0.2)
    await desktop_control.ainvoke({"action": "type_text", "text": "latest AI news today"})
    await desktop_control.ainvoke({"action": "key_press", "key": "enter"})
    
    print("⏳ Waiting for results to load (5s)...")
    await asyncio.sleep(5)
    
    # For the sake of a clean test, we'll simulate "extracting" a summary 
    # but we'll use actual clipboard operations to verify the pipe.
    news_summary = "🤖 [EvoLoop E2E Test] Latest AI News Summary:\n1. OpenAI announces new Sora updates.\n2. Google Gemini 1.5 Pro performance benchmarks released.\n3. Antigravity Agent successfully integrated window-aware vision."
    
    print("📋 Saving summary to clipboard...")
    subprocess.run(["pbcopy"], input=news_summary.encode("utf-8"), check=True)
    
    # --- PHASE 2: WeChat Navigation ---
    print("\n📱 Step 2: Opening WeChat and locating 'File Transfer Assistant'...")
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(1)
    
    info_str = await desktop_control.ainvoke({"action": "get_active_app"})
    data = ast.literal_eval(info_str.replace("Active Application: ", ""))
    bounds_str = data.get("bounds")
    win_x, win_y, _, _ = map(int, bounds_str.split(","))

    # Look for the target in the list (sidebar)
    print("🧠 Scanning WeChat sidebar...")
    screenshot_result = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
    screenshot_path = screenshot_result.split("\n")[0].replace("Screenshot saved to: ", "")
    
    target_pos = None
    try:
        provider = MacOSVisionOCRProvider()
        result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
        
        for el in result.elements:
            if "文件传输助手" in (el.text or ""):
                target_pos = (win_x + el.x, win_y + el.y)
                print(f"✅ Found '文件传输助手' in sidebar at {target_pos}")
                break
        
        if not target_pos:
            print("🔍 '文件传输助手' not in recent list. Using Search...")
            await desktop_control.ainvoke({"action": "key_press", "key": "command+f"})
            await asyncio.sleep(0.3)
            await desktop_control.ainvoke({"action": "type_text", "text": "文件传输助手"})
            await asyncio.sleep(1.5)
            # Re-scan for search result
            res_screenshot = await desktop_control.ainvoke({"action": "screenshot", "region": bounds_str})
            res_path = res_screenshot.split("\n")[0].replace("Screenshot saved to: ", "")
            res_ocr = await provider.process(task=VisionTask.OCR, image_source=res_path)
            for el in res_ocr.elements:
                if "文件传输助手" == (el.text or "").strip() and el.y > 60:
                    target_pos = (win_x + el.x, win_y + el.y)
                    break
            if os.path.exists(res_path): os.remove(res_path)

        if not target_pos:
            print("❌ Failure: Could not find '文件传输助手'.")
            return

        # --- PHASE 3: Paste and Send ---
        print(f"\n⌨️ Step 3: Sending news summary...")
        await desktop_control.ainvoke({"action": "click", "x": target_pos[0], "y": target_pos[1]})
        await asyncio.sleep(0.5)
        
        # Paste and Enter
        await desktop_control.ainvoke({"action": "key_press", "key": "command+v"})
        await asyncio.sleep(0.3)
        await desktop_control.ainvoke({"action": "key_press", "key": "enter"})
        
        print("\n✅ SUCCESS: News sent to WeChat!")
        print("🏁 E2E Flow Complete!")

    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

if __name__ == "__main__":
    asyncio.run(e2e_ai_news_flow())
