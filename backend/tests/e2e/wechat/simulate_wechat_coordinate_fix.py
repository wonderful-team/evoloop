
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.providers.ocr.android_vision import AndroidVisionOCRProvider
from app.core.vision.types import VisionTask
from app.infrastructure.drivers.adb import adb_driver

async def simulate_and_compare():
    print("📸 Taking a live Android screenshot for comparison...")
    screenshot = adb_driver.screenshot()
    
    # We create two providers
    macos_p = MacOSVisionOCRProvider() # Inherits host scale (likely 1.0 or 2.0)
    android_p = AndroidVisionOCRProvider() # FORCES 1.0
    
    # Let's perform detection
    print("\n--- 1. Perception Logic Results ---")
    res_m = await macos_p.process(VisionTask.OCR, screenshot)
    res_a = await android_p.process(VisionTask.OCR, screenshot)
    
    # Find a common element like "微信" or "通讯录"
    target = "微信"
    el_m = next((e for e in res_m.elements if target in e.text), None)
    el_a = next((e for e in res_a.elements if target in e.text), None)
    
    if el_m and el_a:
        print(f"Target UI Element: '{target}'")
        print(f"  [MacOSProvider]   detected at ({el_m.x}, {el_m.y})")
        print(f"  [AndroidProvider] detected at ({el_a.x}, {el_a.y})")
        
        if el_m.x != el_a.x:
            print("\n🚨 COORDINATE MISMATCH DETECTED!")
            print(f"  Reason: MacOSProvider is scaling for Retina points, while AndroidProvider is using absolute pixels.")
            print(f"  Difference: {el_a.x - el_m.x}px on X axis.")
        else:
            print("\n✅ NO COORDINATE MISMATCH on this machine (Host Scale = 1.0).")
            print("  Simulation: If this host were a Retina Mac (2.0x), the MacOSProvider would return:")
            print(f"  ({int(el_a.x/2)}, {int(el_a.y/2)}) which would BE WRONG for Android tapping.")
    
    # Check for "Q" (Search Icon)
    q_a = next((e for e in res_a.elements if '"Q"' in e.text or e.text.strip() == "Q"), None)
    if q_a:
        print(f"\n🎯 Search Icon ('Q') Found at ({q_a.x}, {q_a.y})")
    else:
        print("\n⚠️ Search Icon ('Q') remains undetected in this current UI state.")
        # Diagnostic: print elements near top right
        print("Diagnostic: Top-Right elements (x > 800, y < 400):")
        for e in sorted(res_a.elements, key=lambda x: (x.y, x.x)):
            if e.x > 800 and e.y < 400:
                print(f"  '{e.text}' at ({e.x}, {e.y}) [conf: {e.confidence:.2f}]")

if __name__ == "__main__":
    asyncio.run(simulate_and_compare())
