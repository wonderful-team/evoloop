import asyncio
import base64
import os

from app.domain.tools.vision import analyze_image


async def verify():
    print("🚀 Starting Vision Tool Verification...")

    # 1. Create a dummy 1x1 pixel image
    img_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGP6DwABBAEAAAAA")
    test_path = os.path.abspath("test_vision_pixel.png")

    with open(test_path, "wb") as f:
        f.write(img_data)

    print(f"✅ Created test image at: {test_path}")

    try:
        # 2. Test analyze_image
        print("🔍 Invoking analyze_image...")

        # We need to invoke the tool properly. Since it's a structural tool, we can call invoke or the func directly if we pass context.
        # But analyze_image is a @tool function.
        # Direct async call:
        result = await analyze_image.ainvoke({"image_source": test_path, "question": "What is this image? Is it a white pixel?"})

        print(f"📝 Result: {result}")
        print("✅ Vision Tool executed successfully.")

    except Exception as e:
        print(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if os.path.exists(test_path):
            os.remove(test_path)
            print("🧹 Cleaned up test file.")

if __name__ == "__main__":
    asyncio.run(verify())
