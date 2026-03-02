import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("."))

from app.domain.tools.environment.desktop import desktop_control
from app.infrastructure.drivers.macos import macos_driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def run_scenario():
    print("🚀 Starting AI News Scenario...")
    
    try:
        # 1. Open Google Chrome and Search
        print("\n[Step 1] Opening Chrome and searching for AI news...")
        # Focus Chrome
        await desktop_control.ainvoke({"action": "open_app", "app_name": "Google Chrome"})
        await asyncio.sleep(2)
        
        # Type search query (assuming address bar is focused or using key shortcut)
        # CMD+L to focus address bar
        macos_driver.key_press("command+l")
        await asyncio.sleep(1)
        await desktop_control.ainvoke({"action": "type_text", "text": "latest AI news today"})
        macos_driver.key_press("enter")
        print("✅ Search initiated.")
        await asyncio.sleep(5) # Wait for page load
        
        # 2. Extract a summary (For now, we'll just grab the top text or use a dummy summary)
        print("\n[Step 2] Extracting summary...")
        summary = "Today's AI News: New LLM models released with improved reasoning and multi-modal capabilities."
        macos_driver.set_clipboard(summary)
        print(f"✅ Summary saved to clipboard: {summary}")
        
        # 3. Open WeChat and Send
        print("\n[Step 3] Opening WeChat and sending to File Transfer Assistant...")
        await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
        await asyncio.sleep(2)
        
        # Click "文件传输助手" (文件传输助手)
        print("Attempting to find '文件传输助手' in WeChat (using OCR fallback)...")
        res = await desktop_control.ainvoke({
            "action": "click", 
            "element_name": "文件传输助手", 
            "force_ocr": True
        })
        print(f"Click Result: {res}")
        await asyncio.sleep(1)
        
        # Paste and Send
        # First, ensure focus is in the chat box. We'll try to find it or just CMD+V.
        macos_driver.key_press("command+v")
        await asyncio.sleep(0.5)
        macos_driver.key_press("enter")
        print("✅ Message sent to File Transfer Assistant.")
        
        print("\n🎉 Scenario completed successfully!")

    except Exception as e:
        print(f"❌ Scenario failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_scenario())
