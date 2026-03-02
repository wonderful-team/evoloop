
import asyncio
import os
import sys
import logging
import re

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.providers.ocr.android_vision import AndroidVisionOCRProvider
from app.core.vision.types import VisionTask
from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.drivers.macos import macos_driver

logging.basicConfig(level=logging.ERROR) # Suppress normal logs for cleaner output

async def compare():
    # 1. Capture a fresh screenshot
    print(f"[{time.strftime('%H:%M:%S')}] 📸 Capturing Android screenshot...")
    screenshot = adb_driver.screenshot()
    print(f"Captured: {screenshot}")

    # 2. Setup providers
    macos_p = MacOSVisionOCRProvider()
    android_p = AndroidVisionOCRProvider()

    # 3. Host Info
    host_scale = macos_driver.get_ui_scale_factor()
    print(f"\n🖥️ Host Machine Logic: Scale Factor = {host_scale}")

    # 4. Run comparison
    results = {}
    for name, p in [("MacOSVisionOCRProvider", macos_p), ("AndroidVisionOCRProvider", android_p)]:
        print(f"\n--- {name} ---")
        scale = p._get_ui_scale_factor()
        print(f"Applied Scale: {scale}")
        
        start = time.time()
        res = await p.process(VisionTask.OCR, screenshot)
        duration = time.time() - start
        
        if res.success:
            print(f"Count: {len(res.elements)} (Latency: {duration:.2f}s)")
            # Print top area items (y < 400)
            top_items = sorted([e for e in res.elements if e.y < 400], key=lambda e: (e.y, e.x))
            print("Top-area elements (y < 400):")
            for el in top_items:
                # Highlight potential symbol matches
                marker = "🎯" if '"Q"' in el.text or el.text.strip() in ["Q", "0", "O", "o", "%"] else "  "
                print(f"{marker} {el.text:<20} at ({el.x:<4}, {el.y:<4}) [conf: {el.confidence:.2f}]")
            results[name] = res.elements
        else:
            print(f"❌ {name} Failed: {res.metadata.get('error')}")

    # 5. Coordinate Comparison Analysis
    print("\n" + "="*60)
    print("📊 COORDINATE SCALING ANALYSIS")
    print("="*60)
    
    # Check if they are scaling differently for the SAME element
    # We find an element with same text
    m_els = results.get("MacOSVisionOCRProvider", [])
    a_els = results.get("AndroidVisionOCRProvider", [])
    
    common_text = "微信"
    m_match = next((e for e in m_els if common_text in e.text), None)
    a_match = next((e for e in a_els if common_text in e.text), None)
    
    if m_match and a_match:
        print(f"Target Element: '{common_text}'")
        print(f"  MacOS   Pos: ({m_match.x}, {m_match.y})")
        print(f"  Android Pos: ({a_match.x}, {a_match.y})")
        if m_match.x != a_match.x:
            ratio = a_match.x / m_match.x if m_match.x > 0 else 0
            print(f"  🚀 SCALING DIFFERENCE DETECTED: Ratio = {ratio:.2f}")
        else:
            print("  ✅ COORDINATES MATCH EXACTLY (No scaling difference on this host)")
    else:
        print("Could not find common element '微信' for comparison.")

if __name__ == "__main__":
    import time
    asyncio.run(compare())
