import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.infrastructure.drivers.browser import browser_manager
from app.core.environment.controllers.browser_controller import BrowserController

async def test_reconnect():
    print("🚀 Starting Browser Reconnect Test...")
    
    try:
        # 1. Start browser
        print("\n--- Step 1: Initializing Browser ---")
        page = await browser_manager.get_page()
        print(f"Browser started. Active URL: {page.url}")
        
        # 2. Simulate manual cleanup (without resetting singleton)
        print("\n--- Step 2: Manually closing browser context (simulating crash) ---")
        if browser_manager._browser:
            await browser_manager._browser.close()
        print("Browser context closed, but browser_manager._context is still set.")
        
        # 3. Try to perform an action
        print("\n--- Step 3: Performing navigate action (should trigger auto-reconnect) ---")
        res = await BrowserController.execute(action="navigate", url="https://www.google.com", continue_on_error=False)
        print(f"Result: {res}")
        
        if "google.com" in res:
            print("\n✅ SUCCESS: Browser automatically reconnected and navigated.")
        else:
            print(f"\n❌ FAILURE: Unexpected result: {res}")

    except Exception as e:
        print(f"\n❌ Test Failed with error: {e}")
    finally:
        print("\n--- Step 4: Final Cleanup ---")
        await browser_manager.close()
        print("✅ Done.")

if __name__ == "__main__":
    asyncio.run(test_reconnect())
