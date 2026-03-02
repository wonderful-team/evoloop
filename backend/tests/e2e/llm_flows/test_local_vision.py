import asyncio
import os
import sys
import logging

# Add project root to path
sys.path.append(os.getcwd())

from app.core.vision.engine import vision_engine
from app.core.vision.types import VisionTask
from app.core.config import settings

async def test_local_vision():
    """
    Test script to verify local VLM (screenshot recognition) with a real screenshot.
    """
    from app.infrastructure.drivers.macos import macos_driver
    
    logging.basicConfig(level=logging.INFO)
    print("="*50)
    print("🚀 Local Vision (VLM) Live Verification")
    print("="*50)

    # 1. Capture a real screenshot
    print(f"📸 Capturing live screenshot...")
    try:
        test_image = macos_driver.screenshot()
        print(f"✅ Screenshot saved to: {test_image}")
    except Exception as e:
        print(f"❌ Screenshot failed: {e}")
        return

    print(f"📊 Config Info:")
    print(f"   - SSM Model: {settings.SSM_MODEL_NAME}")
    print(f"   - SSM Base URL: {settings.SSM_API_BASE}")

    print(f"\n🔍 Invoking local VLM for analysis...")
    # This should trigger MultimodalVLMProvider -> VisionLLMFactory -> LLMFactory with local overrides
    result = await vision_engine.process(
        task=VisionTask.ANALYZE,
        image_source=test_image,
        prompt="请分析这张屏幕截图，告诉我你看到了什么（对应的应用、主要的 UI 元素等）。"
    )

    if result.success:
        print(f"\n✅ Vision Inference Successful!")
        print(f"   - Provider Used: {result.metadata.get('model', 'unknown')}")
        print("-" * 30)
        print(f"💡 AI Analysis Result:\n{result.summary}")
        print("-" * 30)
    else:
        print(f"❌ Vision Process Failed: {result.metadata.get('error')}")

    # Cleanup (Optional)
    # if os.path.exists(test_image):
    #     os.remove(test_image)

if __name__ == "__main__":
    asyncio.run(test_local_vision())
