import asyncio
import logging
from app.domain.tools.environment.drivers.macos import macos_driver

logging.basicConfig(level=logging.INFO)

async def verify_shortcuts():
    print("=== Verifying MacOS Shortcuts ===")
    
    try:
        # 1. Test single alphanumeric key
        print("Testing: key_press('a')")
        macos_driver.key_press("a")
        
        # 2. Test special key
        print("Testing: key_press('enter')")
        macos_driver.key_press("enter")
        
        # 3. Test combination (Shortcut)
        print("Testing: key_press('command+a')")
        macos_driver.key_press("command+a")
        
        # 4. Test complex combination
        print("Testing: key_press('shift+tab')")
        macos_driver.key_press("shift+tab")
        
        print("\n✅ All tests passed (check your active window for effect)!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_shortcuts())
