import asyncio
import os
import logging
from app.domain.tools.environment.browser import browser_control

# Configure logging to see the errors
logging.basicConfig(level=logging.INFO)

async def test_screenshot_optimizations():
    print("--- Testing Browser Screenshot Optimizations ---")
    
    url = "https://www.thepaper.cn/newsDetail_forward_32648223"
    
    # Test 1: Successful screenshot with target URL
    print(f"\n[Test 1] Navigating to {url}...")
    await browser_control.ainvoke({"action": "navigate", "url": url})
    
    print("[Test 1] Taking screenshot with animations disabled...")
    result = await browser_control.ainvoke({"action": "screenshot", "timeout_ms": 30000})
    
    if "Screenshot saved to:" in result:
        print("✅ Test 1 Passed: Screenshot captured successfully.")
        # Extract path
        path = result.split("Screenshot saved to: ")[1].split("\n")[0]
        if os.path.exists(path):
            print(f"   Image verified at: {path}")
    else:
        print(f"❌ Test 1 Failed: {result}")

    # Test 2: Verify timeout handling with an impossibly short timeout
    print("\n[Test 2] Verifying timeout handling (timeout_ms=1)...")
    result = await browser_control.ainvoke({"action": "screenshot", "timeout_ms": 1})
    
    if "Error: Screenshot failed" in result and "timeout=1ms" in result:
        print("✅ Test 2 Passed: Timeout correctly handled and reported.")
    else:
        print(f"❌ Test 2 Failed: Unexpected response: {result}")

    # Clean up
    await browser_control.ainvoke({"action": "close"})
    print("\n--- Testing Complete ---")

if __name__ == "__main__":
    asyncio.run(test_screenshot_optimizations())
