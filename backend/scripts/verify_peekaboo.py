import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("."))

from app.infrastructure.drivers.macos import macos_driver

logging.basicConfig(level=logging.INFO)

def test_peekaboo_integration():
    try:
        # 1. Test AX Tree Dump
        print("--- Testing AX Tree Dump ---")
        tree = macos_driver.dump_ax_tree(use_cache=False)
        print(f"Tree length: {len(tree)} characters")
        if "id" in tree:
            print("✅ Found 'id' in AX tree elements")
        else:
            print("❌ No 'id' found in AX tree elements")

        # 2. Test Window Info (Verify if Peekaboo improved it)
        print("\n--- Testing App Info ---")
        app_info = macos_driver.get_current_app()
        print(f"Current App: {app_info.get('name')} ({app_info.get('bundle_id')})")
        
        # 3. Test Screen Size
        print("\n--- Testing Screen Size ---")
        w, h = macos_driver.get_screen_size()
        print(f"Screen Size: {w}x{h}")

    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_peekaboo_integration()
