import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

try:
    print("Testing import of browser_control...")
    from app.domain.tools.environment.browser import browser_control
    print(f"Success! Tool name: {browser_control.name}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\nTesting import of mobile_control...")
    from app.domain.tools.environment.mobile import mobile_control
    print(f"Success! Tool name: {mobile_control.name}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
