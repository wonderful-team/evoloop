import asyncio
import os
import sys

# Add the project root to sys.path if needed
sys.path.append(os.getcwd())

from app.domain.tools.environment.browser import browser_control

async def manual_test():
    print("🚀 Starting Manual Browser Test (Native Linkage Mode)...")
    print("\n💡 NOTE: To test 'Takeover' mode, please launch Chrome first using this command (optimized for ARM Mac):")
    print('   arch -arm64 /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir="/Users/huangjinhuan/Library/Application Support/Google/Chrome-Automation"')
    print("\nIf you don't do this, it will fall back to 'Launch' mode (separate App).")
    
    try:
        # 1. Initialize and check mode
        print("\n--- Step 1: Initializing Browser ---")
        # We trigger initialization by calling a simple action
        url_res = await browser_control.ainvoke({"action": "get_url"})
        print(f"Initial State: {url_res}")
        
        # 2. Navigate
        print("\n--- Step 2: Navigating to Taobao ---")
        nav_res = await browser_control.ainvoke({
            "action": "navigate",
            "url": "https://www.taobao.com"
        })
        print(nav_res)

        # 3. Wait and Screenshot
        print("\n--- Step 3: Waiting 3s and taking Screenshot ---")
        await asyncio.sleep(3)
        screenshot_res = await browser_control.ainvoke({"action": "screenshot"})
        print(screenshot_res)

    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
    finally:
        # 4. Close (Disconnects if CDP, Closes if Launched)
        print("\n--- Step 4: Cleaning Up ---")
        await browser_control.ainvoke({"action": "close"})
        print("✅ Done.")

if __name__ == "__main__":
    asyncio.run(manual_test())
